from pathlib import Path

import pytest
from httpx import AsyncClient

from service.caea_resilience import db
from service.caea_resilience import repository as repo


@pytest.fixture
def isolated_state_db(tmp_path, monkeypatch):
    state_db = tmp_path / "afrelay_state.db"
    monkeypatch.setattr(db, "DB_PATH", Path(state_db))
    db.init_db()
    return state_db


@pytest.mark.asyncio
async def test_queue_solicitar_and_list_outbox(client: AsyncClient, override_auth, isolated_state_db):
    resp = await client.post(
        "/wsfe/caea/queue/solicitar",
        json={"Cuit": 30740253022, "Periodo": 202602, "Orden": 1},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "queued"
    assert body["cycle"]["status"] == "requested"

    outbox_resp = await client.get("/wsfe/caea/queue/outbox")
    assert outbox_resp.status_code == 200
    outbox_body = outbox_resp.json()
    assert outbox_body["status"] == "ok"
    assert len(outbox_body["items"]) >= 1

    active_resp = await client.get("/wsfe/caea/queue/active?cuit=30740253022")
    assert active_resp.status_code == 200
    active_body = active_resp.json()
    assert active_body["status"] == "ok"
    assert len(active_body["cycles"]) == 2


@pytest.mark.asyncio
async def test_issue_local_reserves_number_and_queues_job(client: AsyncClient, override_auth, isolated_state_db):
    cycle_resp = await client.post(
        "/wsfe/caea/queue/solicitar",
        json={"Cuit": 30740253022, "Periodo": 202602, "Orden": 1},
    )
    cycle_id = cycle_resp.json()["cycle"]["id"]
    repo.update_cycle_from_afip(cycle_id, {"ResultGet": {"CAEA": "61234567890123"}}, status="active")

    request_payload = {
        "CycleId": cycle_id,
        "Cuit": 30740253022,
        "PtoVta": 1,
        "CbteTipo": 11,
        "FeCAEARegInfReq": {
            "FeCabReq": {"CantReg": 1, "PtoVta": 1, "CbteTipo": 11},
            "FeDetReq": {
                "FECAEADetRequest": [
                    {
                        "Concepto": 1,
                        "DocTipo": 99,
                        "DocNro": 0,
                        "CbteDesde": 0,
                        "CbteHasta": 0,
                        "CbteFch": "20260202",
                        "ImpTotal": 100.0,
                        "ImpNeto": 100.0,
                        "ImpTotConc": 0.0,
                        "ImpOpEx": 0.0,
                        "ImpTrib": 0.0,
                        "ImpIVA": 0.0,
                        "MonId": "PES",
                        "MonCotiz": 1,
                        "CondicionIVAReceptorId": 5,
                        "CAEA": "61234567890123",
                    }
                ]
            },
        },
    }
    resp = await client.post("/wsfe/caea/queue/issue-local", json=request_payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "queued"
    assert body["reserved_cbte_nro"] == 1
    assert body["caea"] == "61234567890123"
    assert body["invoice"]["status"] == "issued_local"


@pytest.mark.asyncio
async def test_manual_retry_endpoint(client: AsyncClient, override_auth, isolated_state_db, monkeypatch):
    async def fake_process(limit: int = 20):
        return {"processed": 1, "done": 1, "retried": 0, "failed": 0}

    monkeypatch.setattr(
        "service.api.wsfe_caea_resilience.process_pending_outbox_jobs",
        fake_process,
    )

    resp = await client.post("/wsfe/caea/queue/retry?limit=5")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["result"]["done"] == 1


@pytest.mark.asyncio
async def test_issue_local_requires_active_cycle(client: AsyncClient, override_auth, isolated_state_db):
    cycle_resp = await client.post(
        "/wsfe/caea/queue/solicitar",
        json={"Cuit": 30740253022, "Periodo": 202602, "Orden": 1},
    )
    cycle_id = cycle_resp.json()["cycle"]["id"]

    request_payload = {
        "CycleId": cycle_id,
        "Cuit": 30740253022,
        "PtoVta": 1,
        "CbteTipo": 11,
        "FeCAEARegInfReq": {
            "FeCabReq": {"CantReg": 1, "PtoVta": 1, "CbteTipo": 11},
            "FeDetReq": {"FECAEADetRequest": [{"CbteDesde": 0, "CbteHasta": 0}]},
        },
    }
    resp = await client.post("/wsfe/caea/queue/issue-local", json=request_payload)
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_solicit_without_caea_is_not_marked_active(client: AsyncClient, override_auth, isolated_state_db, monkeypatch):
    cycle_resp = await client.post(
        "/wsfe/caea/queue/solicitar",
        json={"Cuit": 30740253022, "Periodo": 202602, "Orden": 2},
    )
    cycle_id = cycle_resp.json()["cycle"]["id"]

    async def fake_solicit(_payload):
        return {
            "status": "success",
            "response": {
                "ResultGet": None,
                "Errors": {"Err": [{"Code": 15006, "Msg": "Del 11/02/2026 hasta 28/02/2026"}]},
                "Events": None,
            },
        }

    monkeypatch.setattr("service.caea_resilience.outbox_worker.caea_solicitar", fake_solicit)

    retry_resp = await client.post("/wsfe/caea/queue/retry?limit=10")
    assert retry_resp.status_code == 200
    result = retry_resp.json()["result"]
    assert result["retried"] >= 1

    active_resp = await client.get("/wsfe/caea/queue/active?cuit=30740253022")
    assert active_resp.status_code == 200
    second_half = [c for c in active_resp.json()["cycles"] if c["periodo"] == 202602 and c["orden"] == 2][0]
    assert second_half["active"] is False

    outbox = await client.get("/wsfe/caea/queue/outbox?status=retrying&limit=20")
    assert outbox.status_code == 200
    assert any(item["idempotency_key"].endswith(":202602:2") for item in outbox.json()["items"])
