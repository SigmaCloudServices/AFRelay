import asyncio
from pathlib import Path

import pytest

from service.caea_resilience import db, outbox_worker
from service.caea_resilience import repository as repo

CUIT = 30575099943


@pytest.fixture
def isolated_state_db(tmp_path, monkeypatch):
    state_db = tmp_path / "afrelay_state.db"
    monkeypatch.setattr(db, "DB_PATH", Path(state_db))
    db.init_db()
    return state_db


def _payload(pv=98, tipo=6):
    return {
        "FeCabReq": {"CantReg": 1, "PtoVta": pv, "CbteTipo": tipo},
        "FeDetReq": {"FECAEADetRequest": [{"CbteDesde": 0, "CbteHasta": 0, "CbteFch": "20261024"}]},
    }


def _inform_resp(resultado):
    return {"status": "success", "response": {
        "FeCabResp": {"Resultado": resultado},
        "FeDetResp": {"FECAEADetResponse": [{"Resultado": resultado}]}}}


def _invoice(invoice_id):
    return next(i for i in repo.list_invoices(CUIT) if i["id"] == invoice_id)


def _job(job_id):
    return next(j for j in repo.list_outbox(limit=500) if j["id"] == job_id)


def _issue():
    cycle = repo.create_cycle(CUIT, 202610, 2)
    return repo.issue_local_invoice(cycle["id"], CUIT, 98, 6, _payload(), seed_last_nro=None)


def _inform_job_for(row):
    return repo.add_outbox_job("INFORM_CAEA_MOVEMENT", f"inform:{CUIT}:98:6:{row['cbte_nro']}",
                               {"invoice_id": row["id"], "request": {}})


# --- Critical 1: atomic claim + guarded terminal states -------------------------------

@pytest.mark.asyncio
async def test_two_concurrent_runners_inform_once(isolated_state_db, monkeypatch):
    row = _issue()
    _inform_job_for(row)
    # both runners got the same (stale) batch before either reached the job
    snapshot = repo.fetch_due_outbox_jobs(limit=50)
    assert len(snapshot) == 1
    monkeypatch.setattr(outbox_worker.repo, "fetch_due_outbox_jobs", lambda limit=20: [dict(j) for j in snapshot])
    calls = []

    async def slow_inform(_payload):
        calls.append(1)
        await asyncio.sleep(0.01)
        return _inform_resp("R" if len(calls) > 1 else "A")

    monkeypatch.setattr(outbox_worker, "_run_inform", slow_inform)
    await asyncio.gather(outbox_worker.process_pending_outbox_jobs(), outbox_worker.process_pending_outbox_jobs())
    assert len(calls) == 1
    assert _invoice(row["id"])["status"] == "informed"


def test_terminal_invoice_states_are_not_overwritten(isolated_state_db):
    informed = _issue()
    rejected = repo.issue_local_invoice(informed["cycle_id"], CUIT, 98, 6, _payload(), seed_last_nro=None)
    repo.mark_invoice_informed(informed["id"], {"ok": 1}, "")
    repo.mark_invoice_rejected(rejected["id"], {"ok": 0}, "10016: fecha")

    for inv_id in (informed["id"], rejected["id"]):
        repo.mark_invoice_rejected(inv_id, {"late": 1}, "already informed")
        repo.mark_invoice_error(inv_id, "late error")
        repo.mark_invoice_informed(inv_id, {"late": 1}, "")
    assert _invoice(informed["id"])["status"] == "informed"
    assert _invoice(informed["id"])["response"] == {"ok": 1}
    assert _invoice(rejected["id"])["status"] == "rejected"
    assert _invoice(rejected["id"])["last_error"] == "10016: fecha"


def test_claim_outbox_job_is_exclusive(isolated_state_db):
    job = repo.add_outbox_job("SOLICIT_CAEA", "solicit:x", {"cycle_id": 1, "cycle": {}})
    assert repo.claim_outbox_job(job["id"]) is True
    assert repo.claim_outbox_job(job["id"]) is False
