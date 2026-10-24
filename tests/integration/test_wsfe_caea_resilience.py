import threading
from pathlib import Path
from unittest.mock import AsyncMock

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
async def test_issue_local_reserves_number_and_queues_job(client: AsyncClient, override_auth, isolated_state_db, monkeypatch):
    monkeypatch.setattr(
        "service.api.wsfe_caea_resilience.get_last_authorized_info",
        AsyncMock(return_value={"status": "success", "response": {"CbteNro": 0}}),
    )
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


def _payload(pv=98, tipo=6):
    return {
        "FeCabReq": {"CantReg": 1, "PtoVta": pv, "CbteTipo": tipo},
        "FeDetReq": {"FECAEADetRequest": [{"CbteDesde": 0, "CbteHasta": 0, "CbteFch": "20261024"}]},
    }


def test_issue_local_invoice_numbers_are_unique_under_concurrency(isolated_state_db):
    cycle = repo.create_cycle(30575099943, 202610, 2)
    results, errors = [], []

    def worker():
        try:
            results.append(repo.issue_local_invoice(cycle["id"], 30575099943, 98, 6, _payload(), seed_last_nro=None)["cbte_nro"])
        except Exception as exc:  # pragma: no cover - surfaced by the assert below
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert sorted(results) == list(range(1, 21))


def test_issue_local_invoice_starts_after_arca_last_authorized(isolated_state_db):
    cycle = repo.create_cycle(30575099943, 202610, 2)
    row = repo.issue_local_invoice(cycle["id"], 30575099943, 98, 6, _payload(), seed_last_nro=41)
    assert row["cbte_nro"] == 42
    # once there are local rows the seed is ignored
    row = repo.issue_local_invoice(cycle["id"], 30575099943, 98, 6, _payload(), seed_last_nro=0)
    assert row["cbte_nro"] == 43


def test_cycle_stores_validity_dates(isolated_state_db):
    cycle = repo.create_cycle(30575099943, 202610, 2)
    repo.update_cycle_from_afip(cycle["id"], {"ResultGet": {
        "CAEA": "61234567890123", "FchVigDesde": "20261016", "FchVigHasta": "20261031", "FchTopeInf": "20261108"}})
    stored = repo.get_cycle_by_id(cycle["id"])
    assert (stored["fch_vig_desde"], stored["fch_vig_hasta"], stored["fch_tope_inf"]) == ("20261016", "20261031", "20261108")
    assert repo.find_cycle_for_date(30575099943, "20261024")["id"] == cycle["id"]
    assert repo.find_cycle_for_date(30575099943, "20261101") is None


@pytest.mark.asyncio
async def test_issue_local_without_cycle_id_uses_cycle_of_cbte_fch(client, override_auth, isolated_state_db, monkeypatch):
    cycle = repo.create_cycle(30575099943, 202610, 2)
    repo.update_cycle_from_afip(cycle["id"], {"ResultGet": {
        "CAEA": "61234567890123", "FchVigDesde": "20261016", "FchVigHasta": "20261031", "FchTopeInf": "20261108"}})
    monkeypatch.setattr(
        "service.api.wsfe_caea_resilience.get_last_authorized_info",
        AsyncMock(return_value={"status": "success", "response": {"CbteNro": 0}}),
    )
    body = {"Cuit": 30575099943, "PtoVta": 98, "CbteTipo": 6, "FeCAEARegInfReq": {
        "FeCabReq": {"CantReg": 1, "PtoVta": 98, "CbteTipo": 6},
        "FeDetReq": {"FECAEADetRequest": [{"CbteDesde": 0, "CbteHasta": 0, "CbteFch": "20261024"}]}}}
    resp = await client.post("/wsfe/caea/queue/issue-local", json=body)
    assert resp.status_code == 200
    assert resp.json()["invoice"]["cycle_id"] == cycle["id"]

    active = (await client.get("/wsfe/caea/queue/active?cuit=30575099943")).json()
    assert all("cycle_id" in c for c in active["cycles"])


def _queue_inform_job(response, monkeypatch):
    from service.caea_resilience import outbox_worker

    cycle = repo.create_cycle(30575099943, 202610, 2)
    row = repo.issue_local_invoice(cycle["id"], 30575099943, 98, 6, _payload(), seed_last_nro=None)
    job = repo.add_outbox_job("INFORM_CAEA_MOVEMENT", f"inform:{row['id']}", {"invoice_id": row["id"], "request": {}})
    monkeypatch.setattr(outbox_worker, "_run_inform", AsyncMock(return_value=response))
    return outbox_worker, row, job


def _inform_resp(resultado, errors=None):
    return {"status": "success", "response": {
        "FeCabResp": {"Resultado": resultado},
        "FeDetResp": {"FECAEADetResponse": [{"Resultado": resultado}]},
        "Errors": {"Err": errors} if errors else None}}


def _job_and_invoice(job_id, invoice_id):
    job = next(j for j in repo.list_outbox(limit=50) if j["id"] == job_id)
    invoice = next(i for i in repo.list_invoices(30575099943) if i["id"] == invoice_id)
    return job, invoice


@pytest.mark.asyncio
async def test_worker_rejected_inform_is_terminal(isolated_state_db, monkeypatch):
    worker, row, job = _queue_inform_job(_inform_resp("R", [{"Code": 10016, "Msg": "fecha"}]), monkeypatch)
    result = await worker.process_pending_outbox_jobs()
    assert result["done"] == 1 and result["retried"] == 0
    j, inv = _job_and_invoice(job["id"], row["id"])
    assert j["status"] == "done"
    assert inv["status"] == "rejected" and "10016" in inv["last_error"]


@pytest.mark.asyncio
async def test_worker_accepted_inform_marks_informed(isolated_state_db, monkeypatch):
    worker, row, job = _queue_inform_job(_inform_resp("A"), monkeypatch)
    result = await worker.process_pending_outbox_jobs()
    assert result["done"] == 1
    j, inv = _job_and_invoice(job["id"], row["id"])
    assert j["status"] == "done" and inv["status"] == "informed"


@pytest.mark.asyncio
async def test_worker_errors_only_inform_is_retried_not_rejected(isolated_state_db, monkeypatch):
    resp = {"status": "success", "response": {"Errors": {"Err": [{"Code": 600, "Msg": "token"}]}}}
    worker, row, job = _queue_inform_job(resp, monkeypatch)
    result = await worker.process_pending_outbox_jobs()
    assert result["done"] == 0 and result["retried"] == 1
    j, inv = _job_and_invoice(job["id"], row["id"])
    assert j["status"] == "retrying" and j["attempts"] == 1
    assert inv["status"] != "rejected"


@pytest.mark.asyncio
async def test_list_invoices_exposes_rejected_status(client: AsyncClient, override_auth, isolated_state_db):
    cycle = repo.create_cycle(30575099943, 202610, 2)
    row = repo.issue_local_invoice(cycle["id"], 30575099943, 98, 6, _payload(), seed_last_nro=None)
    repo.mark_invoice_rejected(row["id"], {"status": "success"}, "10016: fecha")

    resp = await client.get("/wsfe/caea/queue/invoices?cuit=30575099943")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == row["id"]
    assert items[0]["status"] == "rejected"
    assert items[0]["last_error"] == "10016: fecha"
    assert items[0]["response"] == {"status": "success"}
