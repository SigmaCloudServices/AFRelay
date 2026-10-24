from pathlib import Path

import pytest

from service.caea_resilience import bootstrap, db
from service.caea_resilience import repository as repo


@pytest.fixture
def isolated_state_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", Path(tmp_path / "s.db"))
    db.init_db()


def _active_cycle():
    cycle = repo.create_cycle(30575099943, 202610, 2)
    repo.update_cycle_from_afip(cycle["id"], {"ResultGet": {
        "CAEA": "61234567890123", "FchVigDesde": "20261016", "FchVigHasta": "20261031", "FchTopeInf": "20261108"}})
    return cycle


def test_sin_movimiento_only_for_closed_cycles_and_unused_pvs(isolated_state_db):
    cycle = _active_cycle()
    repo.set_ptos_venta(30575099943, [98, 99])
    payload = {"FeCabReq": {}, "FeDetReq": {"FECAEADetRequest": [{"CbteFch": "20261020"}]}}
    repo.issue_local_invoice(cycle["id"], 30575099943, 98, 6, payload, seed_last_nro=0)

    assert bootstrap.pending_sin_movimiento("20261031") == []          # cycle still open
    assert bootstrap.pending_sin_movimiento("20261101") == [(cycle["id"], 30575099943, 99, "61234567890123")]

    repo.mark_sin_movimiento(cycle["id"], 99, {"status": "success"})
    assert bootstrap.pending_sin_movimiento("20261101") == []


def test_configured_cuits_include_registered_ptos_venta(isolated_state_db, monkeypatch):
    monkeypatch.setenv("CAEA_BOOTSTRAP_CUITS", "")
    repo.set_ptos_venta(30575099943, [98])
    assert bootstrap._configured_cuits() == [30575099943]


def test_configured_cuits_union_without_duplicates(isolated_state_db, monkeypatch):
    monkeypatch.setenv("CAEA_BOOTSTRAP_CUITS", "30575099943,20111111112")
    repo.set_ptos_venta(30575099943, [98])
    repo.set_ptos_venta(27222222223, [1])
    assert bootstrap._configured_cuits() == [30575099943, 20111111112, 27222222223]


@pytest.mark.asyncio
async def test_inform_sin_movimiento_once_marks_success_and_logs_failure(isolated_state_db, monkeypatch, caplog):
    cycle = _active_cycle()
    repo.set_ptos_venta(30575099943, [98, 99])
    monkeypatch.setattr(bootstrap, "pending_sin_movimiento",
                        lambda today: [(cycle["id"], 30575099943, 98, "61234567890123"),
                                       (cycle["id"], 30575099943, 99, "61234567890123")])
    calls = []

    async def fake_informar(comp):
        calls.append(comp)
        if comp["PtoVta"] == 98:
            return {"status": "success"}
        return {"status": "error", "message": "boom"}

    monkeypatch.setattr(bootstrap, "caea_sin_movimiento_informar", fake_informar)
    warnings = []
    monkeypatch.setattr(bootstrap.logger, "warning", lambda *a, **k: warnings.append(a))
    result = await bootstrap.inform_sin_movimiento_once()

    assert result == {"informed": 1}
    assert {c["PtoVta"] for c in calls} == {98, 99}
    by_pv = {p["pto_vta"]: p for p in repo.list_cycles_with_pvs(30575099943)[0]["ptos_venta"]}
    assert by_pv[98]["sin_movimiento_at"] is not None
    assert by_pv[99]["sin_movimiento_at"] is None
    assert len(warnings) == 1 and "Sin movimiento failed" in warnings[0][0]
