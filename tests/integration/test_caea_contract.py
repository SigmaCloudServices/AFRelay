import copy
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from service.caea_resilience import bootstrap, db, numbering, outbox_worker
from service.caea_resilience import repository as repo

CUIT = 30575099943


@pytest.fixture
def isolated_state_db(tmp_path, monkeypatch):
    state_db = tmp_path / "afrelay_state.db"
    monkeypatch.setattr(db, "DB_PATH", Path(state_db))
    db.init_db()
    return state_db


def _active_cycle(periodo=202610, orden=2, desde="20261016", hasta="20261031", tope="20261108"):
    cycle = repo.create_cycle(CUIT, periodo, orden)
    repo.update_cycle_from_afip(cycle["id"], {"ResultGet": {
        "CAEA": "61234567890123", "FchVigDesde": desde, "FchVigHasta": hasta, "FchTopeInf": tope}})
    return repo.get_cycle_by_id(cycle["id"])


def _body(pv=98, tipo=6, fch="20261024", client_ref=None, cab=None):
    body = {"Cuit": CUIT, "PtoVta": pv, "CbteTipo": tipo, "FeCAEARegInfReq": {
        "FeCabReq": cab if cab is not None else {"CantReg": 1, "PtoVta": pv, "CbteTipo": tipo},
        "FeDetReq": {"FECAEADetRequest": [{"CbteDesde": 0, "CbteHasta": 0, "CbteFch": fch, "ImpTotal": 100.0}]}}}
    if client_ref is not None:
        body["ClientRef"] = client_ref
    return body


def _last_authorized(nro):
    return AsyncMock(return_value={"status": "success", "response": {"PtoVta": 98, "CbteTipo": 6, "CbteNro": nro}})


def _arca_down():
    return AsyncMock(side_effect=OSError("loginTicketResponse.xml not found"))


def _jobs():
    return repo.list_outbox(limit=500)


# --- Item 3: numbering seeded while online ---------------------------------------------

@pytest.mark.asyncio
async def test_put_ptos_venta_seeds_numbering(client, override_auth, isolated_state_db, monkeypatch):
    monkeypatch.setenv("CAEA_CBTE_TIPOS", "6,8")
    seen = []

    async def fake(comp):
        seen.append((comp["PtoVta"], comp["CbteTipo"]))
        return {"status": "success", "response": {"CbteNro": 40 + comp["CbteTipo"]}}

    monkeypatch.setattr(numbering, "get_last_authorized_info", fake)
    resp = await client.put("/wsfe/caea/queue/ptos-venta", json={"Cuit": CUIT, "PtosVenta": [98, 99]})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["seeding"]["seeded"] == 4 and body["seeding"]["errors"] == []
    assert sorted(seen) == [(98, 6), (98, 8), (99, 6), (99, 8)]
    assert repo.get_numbering(CUIT, 98, 6)["last_nro"] == 46
    assert repo.get_numbering(CUIT, 99, 8)["last_nro"] == 48


def test_cbte_tipos_default(monkeypatch):
    monkeypatch.delenv("CAEA_CBTE_TIPOS", raising=False)
    assert numbering.configured_cbte_tipos() == [1, 3, 6, 8]


@pytest.mark.asyncio
async def test_put_ptos_venta_seeding_failure_is_not_raised(client, override_auth, isolated_state_db, monkeypatch):
    monkeypatch.setenv("CAEA_CBTE_TIPOS", "6")
    monkeypatch.setattr(numbering, "get_last_authorized_info", _arca_down())
    resp = await client.put("/wsfe/caea/queue/ptos-venta", json={"Cuit": CUIT, "PtosVenta": [98]})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok" and body["seeding"]["seeded"] == 0
    assert len(body["seeding"]["errors"]) == 1
    assert repo.get_numbering(CUIT, 98, 6) is None


@pytest.mark.asyncio
async def test_seed_does_not_overwrite_when_local_invoices_exist(isolated_state_db, monkeypatch):
    monkeypatch.setenv("CAEA_CBTE_TIPOS", "6")
    cycle = _active_cycle()
    repo.set_ptos_venta(CUIT, [98])
    monkeypatch.setattr(numbering, "get_last_authorized_info", _last_authorized(10))
    await numbering.seed_numbering(CUIT)
    repo.issue_local_invoice(cycle["id"], CUIT, 98, 6, _body()["FeCAEARegInfReq"], seed_last_nro=None)
    monkeypatch.setattr(numbering, "get_last_authorized_info", _last_authorized(500))
    await numbering.seed_numbering(CUIT)
    assert repo.get_numbering(CUIT, 98, 6)["last_nro"] == 10


@pytest.mark.asyncio
async def test_bootstrap_seeds_registered_ptos_venta(isolated_state_db, monkeypatch):
    monkeypatch.setenv("CAEA_CBTE_TIPOS", "6")
    monkeypatch.setenv("CAEA_BOOTSTRAP_CUITS", "")
    repo.set_ptos_venta(CUIT, [98])
    monkeypatch.setattr(numbering, "get_last_authorized_info", _last_authorized(7))
    monkeypatch.setattr(bootstrap, "process_pending_outbox_jobs",
                        AsyncMock(return_value={"processed": 0, "done": 0, "retried": 0, "failed": 0}))
    await bootstrap.bootstrap_caea_cycles_once()
    assert repo.get_numbering(CUIT, 98, 6)["last_nro"] == 7


@pytest.mark.asyncio
async def test_issue_local_uses_seed_when_arca_is_down(client, override_auth, isolated_state_db, monkeypatch):
    monkeypatch.setenv("CAEA_CBTE_TIPOS", "6")
    _active_cycle()
    monkeypatch.setattr(numbering, "get_last_authorized_info", _last_authorized(41))
    assert (await client.put("/wsfe/caea/queue/ptos-venta", json={"Cuit": CUIT, "PtosVenta": [98]})).status_code == 200
    down = _arca_down()
    monkeypatch.setattr(numbering, "get_last_authorized_info", down)
    resp = await client.post("/wsfe/caea/queue/issue-local", json=_body())
    assert resp.status_code == 200
    assert resp.json()["reserved_cbte_nro"] == 42
    down.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("arca", [
    _arca_down(),
    AsyncMock(return_value={"status": "error", "error": {"method": "FECompUltimoAutorizado",
                                                          "error_type": "Network error", "details": "x" * 300}}),
    AsyncMock(return_value={"status": "success", "response": {
        "CbteNro": None, "Errors": {"Err": [{"Code": 600, "Msg": "ValidacionDeToken: no aparecio CUIT"}]}}}),
], ids=["raises", "network-error", "arca-errors"])
async def test_issue_local_503_without_seed_and_arca_unavailable(client, override_auth, isolated_state_db, monkeypatch, arca):
    _active_cycle()
    monkeypatch.setattr(numbering, "get_last_authorized_info", arca)
    resp = await client.post("/wsfe/caea/queue/issue-local", json=_body())
    assert resp.status_code == 503
    detail = resp.json()["detail"]
    assert isinstance(detail, str) and len(detail) < 200 and "{" not in detail
    assert repo.list_invoices(CUIT) == [] and _jobs() == []


# --- Item 4: ClientRef idempotency -----------------------------------------------------

@pytest.mark.asyncio
async def test_issue_local_client_ref_is_idempotent(client, override_auth, isolated_state_db, monkeypatch):
    _active_cycle()
    monkeypatch.setattr(numbering, "get_last_authorized_info", _last_authorized(0))
    first = await client.post("/wsfe/caea/queue/issue-local", json=_body(client_ref="pos1-000123"))
    second = await client.post("/wsfe/caea/queue/issue-local", json=_body(client_ref="pos1-000123"))
    other = await client.post("/wsfe/caea/queue/issue-local", json=_body(client_ref="pos1-000124"))
    assert first.status_code == second.status_code == other.status_code == 200
    assert first.json() == second.json()
    assert first.json()["reserved_cbte_nro"] == 1 and other.json()["reserved_cbte_nro"] == 2
    assert len(repo.list_invoices(CUIT)) == 2 and len(_jobs()) == 2
    assert first.json()["invoice"]["client_ref"] == "pos1-000123"


def test_issue_local_invoice_client_ref_in_repo(isolated_state_db):
    cycle = _active_cycle()
    a = repo.issue_local_invoice(cycle["id"], CUIT, 98, 6, _body()["FeCAEARegInfReq"], None, client_ref="r1")
    b = repo.issue_local_invoice(cycle["id"], CUIT, 98, 6, _body()["FeCAEARegInfReq"], None, client_ref="r1")
    c = repo.issue_local_invoice(cycle["id"], CUIT, 98, 6, _body()["FeCAEARegInfReq"], None)
    d = repo.issue_local_invoice(cycle["id"], CUIT, 98, 6, _body()["FeCAEARegInfReq"], None)
    assert a["id"] == b["id"] and a["cbte_nro"] == 1
    assert (c["cbte_nro"], d["cbte_nro"]) == (2, 3)  # NULL ClientRef never collides


# --- Item 5 + minor: invoice and job in one transaction, request built from stored row ------

def test_issue_local_invoice_creates_its_inform_job(isolated_state_db):
    cycle = _active_cycle()
    payload = _body(cab={"CantReg": 7, "PtoVta": 1, "CbteTipo": 11})["FeCAEARegInfReq"]
    original = copy.deepcopy(payload)
    row = repo.issue_local_invoice(cycle["id"], CUIT, 98, 6, payload, seed_last_nro=41)
    assert payload == original  # caller's dict is not mutated
    jobs = _jobs()
    assert len(jobs) == 1
    job = jobs[0]
    assert job["job_type"] == "INFORM_CAEA_MOVEMENT"
    assert job["idempotency_key"] == f"inform:{CUIT}:98:6:42"
    job_payload = json.loads(job["payload_json"])
    assert job_payload["invoice_id"] == row["id"]
    req = job_payload["request"]
    assert req["Cuit"] == CUIT
    assert req["FeCAEARegInfReq"] == json.loads(row["payload_json"])
    assert req["FeCAEARegInfReq"]["FeCabReq"] == {"CantReg": 1, "PtoVta": 98, "CbteTipo": 6}
    det = req["FeCAEARegInfReq"]["FeDetReq"]["FECAEADetRequest"][0]
    assert (det["CbteDesde"], det["CbteHasta"], det["CAEA"]) == (42, 42, "61234567890123")


def test_issue_local_invoice_rolls_back_invoice_when_job_insert_fails(isolated_state_db):
    cycle = _active_cycle()
    conn = db.get_connection()
    try:  # a conflicting job row makes the in-transaction job insert fail
        conn.execute("CREATE TRIGGER boom BEFORE INSERT ON afip_outbox BEGIN SELECT RAISE(ABORT, 'boom'); END;")
    finally:
        conn.close()
    with pytest.raises(sqlite3.DatabaseError):
        repo.issue_local_invoice(cycle["id"], CUIT, 98, 6, _body()["FeCAEARegInfReq"], seed_last_nro=None)
    assert repo.list_invoices(CUIT) == []


# --- Item 6: stranded processing jobs -----------------------------------------------------

def _set_job(job_id, status, updated_at):
    conn = db.get_connection()
    try:
        conn.execute("UPDATE afip_outbox SET status=?, updated_at=? WHERE id=?", (status, updated_at, job_id))
    finally:
        conn.close()


def test_recover_stranded_processing_jobs(isolated_state_db):
    old = repo.add_outbox_job("SOLICIT_CAEA", "solicit:old", {"cycle_id": 1, "cycle": {}})
    fresh = repo.add_outbox_job("SOLICIT_CAEA", "solicit:fresh", {"cycle_id": 2, "cycle": {}})
    now = datetime.now(timezone.utc)
    _set_job(old["id"], "processing", (now - timedelta(minutes=11)).isoformat())
    _set_job(fresh["id"], "processing", (now - timedelta(minutes=2)).isoformat())
    assert repo.recover_stranded_processing_jobs(older_than_minutes=10) == 1
    by_id = {j["id"]: j for j in _jobs()}
    assert by_id[old["id"]]["status"] == "retrying"
    assert by_id[old["id"]]["next_retry_at"] <= datetime.now(timezone.utc).isoformat()
    assert by_id[fresh["id"]]["status"] == "processing"


@pytest.mark.asyncio
async def test_bootstrap_recovers_stranded_jobs_first(isolated_state_db, monkeypatch):
    monkeypatch.setenv("CAEA_BOOTSTRAP_CUITS", "")
    job = repo.add_outbox_job("SOLICIT_CAEA", "solicit:old", {"cycle_id": 1, "cycle": {}})
    _set_job(job["id"], "processing", "2000-01-01T00:00:00+00:00")
    await bootstrap.bootstrap_caea_cycles_once()
    assert _jobs()[0]["status"] == "retrying"


# --- Item 7: validity dates backfilled for pre-migration cycles ---------------------------

def test_init_db_backfills_validity_of_old_cycles(tmp_path, monkeypatch):
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE caea_cycle (id INTEGER PRIMARY KEY AUTOINCREMENT, cuit INTEGER NOT NULL, periodo INTEGER NOT NULL,
            orden INTEGER NOT NULL, caea_code TEXT, status TEXT NOT NULL, created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL, last_error TEXT);
        INSERT INTO caea_cycle (cuit, periodo, orden, caea_code, status, created_at, updated_at)
            VALUES (30575099943, 202610, 2, '61234567890123', 'active', 'x', 'x'),
                   (30575099943, 202602, 2, '61234567890124', 'active', 'x', 'x'),
                   (30575099943, 202611, 1, '61234567890125', 'active', 'x', 'x'),
                   (30575099943, 202612, 1, NULL, 'requested', 'x', 'x');
        """
    )
    conn.commit()
    conn.close()
    monkeypatch.setattr(db, "DB_PATH", Path(path))
    db.init_db()
    db.init_db()  # idempotent

    assert repo.find_cycle_for_date(CUIT, "20261024")["periodo"] == 202610
    feb = repo.get_cycle(CUIT, 202602, 2)
    assert (feb["fch_vig_desde"], feb["fch_vig_hasta"], feb["fch_tope_inf"]) == ("20260216", "20260228", None)
    nov = repo.get_cycle(CUIT, 202611, 1)
    assert (nov["fch_vig_desde"], nov["fch_vig_hasta"]) == ("20261101", "20261115")
    assert repo.get_cycle(CUIT, 202612, 1)["fch_vig_desde"] is None  # not active: left alone


# --- Item 8: invoice listing reports status changes --------------------------------------

@pytest.mark.asyncio
async def test_list_invoices_updated_since_and_filters(client, override_auth, isolated_state_db):
    cycle = _active_cycle()
    rows = [repo.issue_local_invoice(cycle["id"], CUIT, 98, tipo, _body(tipo=tipo)["FeCAEARegInfReq"], None)
            for tipo in (6, 6, 8)]
    resp = await client.get(f"/wsfe/caea/queue/invoices?cuit={CUIT}")
    assert [i["id"] for i in resp.json()["items"]] == [r["id"] for r in rows]
    cursor = max(i["updated_at"] for i in resp.json()["items"])
    last_id = resp.json()["items"][-1]["id"]

    repo.mark_invoice_informed(rows[0]["id"], {"r": "A"}, "")
    resp = await client.get("/wsfe/caea/queue/invoices",
                            params={"cuit": CUIT, "updated_since": cursor, "since_id": last_id})
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert [(i["id"], i["status"]) for i in items] == [(rows[0]["id"], "informed")]

    # since_id alone still works (id cursor)
    resp = await client.get(f"/wsfe/caea/queue/invoices?cuit={CUIT}&since_id={rows[0]['id']}")
    assert [i["id"] for i in resp.json()["items"]] == [rows[1]["id"], rows[2]["id"]]

    resp = await client.get(f"/wsfe/caea/queue/invoices?cuit={CUIT}&cbte_tipo=8")
    assert [i["id"] for i in resp.json()["items"]] == [rows[2]["id"]]
    resp = await client.get(f"/wsfe/caea/queue/invoices?cuit={CUIT}&cbte_tipo=6&cbte_nro=2")
    assert [i["id"] for i in resp.json()["items"]] == [rows[1]["id"]]

    # an offset timestamp is normalised to UTC
    resp = await client.get("/wsfe/caea/queue/invoices",
                            params={"cuit": CUIT, "updated_since": "2000-01-01T00:00:00-03:00"})
    assert len(resp.json()["items"]) == 3
    assert (await client.get(f"/wsfe/caea/queue/invoices?cuit={CUIT}&updated_since=yesterday")).status_code == 422


def test_updated_since_keyset_breaks_ties_by_id(isolated_state_db):
    cycle = _active_cycle()
    rows = [repo.issue_local_invoice(cycle["id"], CUIT, 98, 6, _body()["FeCAEARegInfReq"], None) for _ in range(3)]
    conn = db.get_connection()
    try:
        conn.execute("UPDATE caea_invoice SET updated_at='2026-10-24T12:00:00.000000+00:00'")
    finally:
        conn.close()
    page1 = repo.list_invoices(CUIT, updated_since="2026-10-24T12:00:00.000000+00:00", limit=2)
    page2 = repo.list_invoices(CUIT, updated_since=page1[-1]["updated_at"], since_id=page1[-1]["id"], limit=2)
    assert [i["id"] for i in page1 + page2] == [r["id"] for r in rows]


# --- Item 9: invoice stays issued_local while the inform retries ------------------------

@pytest.mark.asyncio
async def test_inform_retry_keeps_issued_local_with_last_error(isolated_state_db, monkeypatch):
    cycle = _active_cycle()
    row = repo.issue_local_invoice(cycle["id"], CUIT, 98, 6, _body()["FeCAEARegInfReq"], None)
    monkeypatch.setattr(outbox_worker, "_run_inform", AsyncMock(return_value={"status": "error", "error": "Network error"}))
    result = await outbox_worker.process_pending_outbox_jobs()
    assert result["retried"] == 1
    invoice = repo.list_invoices(CUIT)[0]
    assert invoice["id"] == row["id"]
    assert invoice["status"] == "issued_local"
    assert "Network error" in invoice["last_error"]


# --- Minors -------------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("det", [[], [{"CbteDesde": 0, "CbteHasta": 0}], [{"CbteFch": "2026-10-24"}]],
                         ids=["empty", "no-cbtefch", "bad-cbtefch"])
async def test_issue_local_malformed_payload_is_422(client, override_auth, isolated_state_db, det):
    _active_cycle()
    body = _body()
    body["FeCAEARegInfReq"]["FeDetReq"]["FECAEADetRequest"] = det
    resp = await client.post("/wsfe/caea/queue/issue-local", json=body)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_issue_local_missing_fedetreq_is_422(client, override_auth, isolated_state_db):
    body = _body()
    del body["FeCAEARegInfReq"]["FeDetReq"]
    assert (await client.post("/wsfe/caea/queue/issue-local", json=body)).status_code == 422


@pytest.mark.asyncio
async def test_issue_local_404_when_cbte_fch_outside_every_cycle(client, override_auth, isolated_state_db, monkeypatch):
    _active_cycle()
    monkeypatch.setattr(numbering, "get_last_authorized_info", _last_authorized(0))
    resp = await client.post("/wsfe/caea/queue/issue-local", json=_body(fch="20261201"))
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_issue_local_response_shape(client, override_auth, isolated_state_db, monkeypatch):
    _active_cycle()
    monkeypatch.setattr(numbering, "get_last_authorized_info", _last_authorized(0))
    resp = await client.post("/wsfe/caea/queue/issue-local",
                             json=_body(cab={"CantReg": 3, "PtoVta": 1, "CbteTipo": 11}))
    assert resp.status_code == 200
    body = resp.json()
    assert body["fch_vig_hasta"] == "20261031" and body["fch_tope_inf"] == "20261108"
    assert "payload_json" not in body["invoice"]
    assert body["invoice"]["status"] == "issued_local"
    req = json.loads(_jobs()[0]["payload_json"])["request"]["FeCAEARegInfReq"]
    assert req["FeCabReq"] == {"CantReg": 1, "PtoVta": 98, "CbteTipo": 6}


@pytest.mark.asyncio
async def test_sin_movimiento_after_tope_logs_error_once_and_does_not_call(isolated_state_db, monkeypatch):
    _active_cycle()
    repo.set_ptos_venta(CUIT, [98, 99])
    informar = AsyncMock(return_value={"status": "success", "response": {"Resultado": "A"}})
    monkeypatch.setattr(bootstrap, "caea_sin_movimiento_informar", informar)
    errors = []
    monkeypatch.setattr(bootstrap.logger, "error", lambda *a, **k: errors.append(a))

    assert await bootstrap.inform_sin_movimiento_once(today="20261109") == {"informed": 0}
    informar.assert_not_called()
    assert len(errors) == 1

    errors.clear()
    assert await bootstrap.inform_sin_movimiento_once(today="20261108") == {"informed": 2}
    assert errors == []
