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


def _invalid_invoice_payload():
    return {
        "Auth": {"Cuit": 30740253022},
        "FeCAEReq": {
            "FeCabReq": {"CantReg": 1, "PtoVta": 1, "CbteTipo": 11},
            "FeDetReq": {
                "FECAEDetRequest": [
                    {
                        "Concepto": 1,
                        "DocTipo": 99,
                        "DocNro": 0,
                        "CbteDesde": 2,
                        "CbteHasta": 2,
                        "CbteFch": "2026-01-25",
                        "ImpTotal": 100.0,
                        "ImpNeto": 100.0,
                        "ImpTotConc": 0.0,
                        "ImpOpEx": 0.0,
                        "ImpTrib": 0.0,
                        "ImpIVA": 0.0,
                        "MonId": "PES",
                        "MonCotiz": 1,
                        "CondicionIVAReceptorId": 5,
                    }
                ]
            },
        },
    }


@pytest.mark.asyncio
async def test_ui_metrics_and_logs_endpoints(client: AsyncClient, override_auth):
    invalid_payload = _invalid_invoice_payload()
    invoice_resp = await client.post("/wsfe/invoices", json=invalid_payload)
    assert invoice_resp.status_code == 422
    assert "X-Trace-Id" in invoice_resp.headers

    logs_resp = await client.get("/ui/logs", params={"endpoint": "/wsfe/invoices"})
    assert logs_resp.status_code == 200
    logs_data = logs_resp.json()
    assert logs_data["total"] >= 1
    assert any("/wsfe/invoices" in item["path"] for item in logs_data["items"])

    metrics_resp = await client.get("/ui/metrics/summary")
    assert metrics_resp.status_code == 200
    metrics_data = metrics_resp.json()
    assert "total_requests" in metrics_data
    assert "services" in metrics_data


@pytest.mark.asyncio
async def test_ui_errors_and_alerts_endpoints(client: AsyncClient, override_auth):
    await client.post("/wsfe/invoices", json=_invalid_invoice_payload())

    errors_resp = await client.get("/ui/errors", params={"group_by": "error_type"})
    assert errors_resp.status_code == 200
    errors_data = errors_resp.json()
    assert "items" in errors_data
    assert isinstance(errors_data["items"], list)

    alerts_resp = await client.get("/ui/alerts")
    assert alerts_resp.status_code == 200
    alerts_data = alerts_resp.json()
    assert "active" in alerts_data
    assert "count" in alerts_data


@pytest.mark.asyncio
async def test_ui_tokens_and_operations_endpoints(client: AsyncClient, override_auth):
    token_resp = await client.get("/ui/tokens/status")
    assert token_resp.status_code == 200
    token_data = token_resp.json()
    assert "wsaa" in token_data
    assert "wspci" in token_data

    ops_resp = await client.get("/ui/operations/summary")
    assert ops_resp.status_code == 200
    ops_data = ops_resp.json()
    assert "fecae" in ops_data
    assert "wsfe_params" in ops_data
    assert "actividades" in ops_data["wsfe_params"]
    assert "caea" in ops_data
    assert "domain_events" in ops_data

    events_resp = await client.get("/ui/events", params={"service": "wsfe"})
    assert events_resp.status_code == 200
    events_data = events_resp.json()
    assert "items" in events_data

    queue_resp = await client.get("/ui/caea/queue")
    assert queue_resp.status_code == 200
    queue_data = queue_resp.json()
    assert "summary" in queue_data
    assert "items" in queue_data

    retry_resp = await client.post("/ui/caea/queue/retry?limit=5")
    assert retry_resp.status_code == 200
    retry_data = retry_resp.json()
    assert retry_data["status"] == "ok"


@pytest.mark.asyncio
async def test_ui_caea_assignments_endpoint(client: AsyncClient, override_auth, isolated_state_db):
    cycle = repo.create_cycle(cuit=30740253022, periodo=202602, orden=1)
    repo.update_cycle_from_afip(cycle["id"], {"ResultGet": {"CAEA": "61234567890123"}}, status="active")

    inv_1 = repo.create_local_invoice(
        cycle_id=cycle["id"],
        cuit=30740253022,
        pto_vta=3,
        cbte_tipo=11,
        cbte_nro=501,
        payload={},
    )
    inv_2 = repo.create_local_invoice(
        cycle_id=cycle["id"],
        cuit=30740253022,
        pto_vta=3,
        cbte_tipo=11,
        cbte_nro=502,
        payload={},
    )
    repo.mark_invoice_informed(inv_1["id"])
    repo.mark_invoice_error(inv_2["id"], "forced_error")

    resp = await client.get("/ui/caea/assignments")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] >= 1
    assert len(body["items"]) >= 1

    row = next(item for item in body["items"] if item["periodo"] == 202602 and item["pto_vta"] == 3)
    assert row["caea_code"] == "61234567890123"
    assert row["cbte_from"] == 501
    assert row["cbte_to"] == 502
    assert row["invoices_count"] == 2
    assert row["informed_count"] == 1
    assert row["error_count"] == 1
