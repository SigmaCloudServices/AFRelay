from datetime import datetime, timezone
from pathlib import Path

import pytest

from service.caea_resilience import db
from service.caea_resilience.bootstrap import (bootstrap_caea_cycles_once,
                                               resolve_current_and_next_cycles)
from service.caea_resilience.repository import list_outbox


@pytest.fixture
def isolated_state_db(tmp_path, monkeypatch):
    state_db = tmp_path / "afrelay_state.db"
    monkeypatch.setattr(db, "DB_PATH", Path(state_db))
    db.init_db()
    return state_db


def test_resolve_cycles_first_half_month():
    cycles = resolve_current_and_next_cycles(datetime(2026, 2, 10, 10, 0, tzinfo=timezone.utc))
    assert cycles == [(202602, 1), (202602, 2)]


def test_resolve_cycles_second_half_month():
    cycles = resolve_current_and_next_cycles(datetime(2026, 2, 20, 10, 0, tzinfo=timezone.utc))
    assert cycles == [(202602, 2), (202603, 1)]


@pytest.mark.asyncio
async def test_bootstrap_queues_jobs_when_cuit_configured(isolated_state_db, monkeypatch):
    monkeypatch.setenv("CAEA_BOOTSTRAP_CUITS", "30740253022")

    async def fake_process(limit: int = 100):
        return {"processed": 0, "done": 0, "retried": 0, "failed": 0}

    monkeypatch.setattr("service.caea_resilience.bootstrap.process_pending_outbox_jobs", fake_process)

    result = await bootstrap_caea_cycles_once()
    assert result["status"] == "ok"
    assert result["summary"]["processed_cuits"] == 1
    assert result["summary"]["ensured_cycles"] == 2

    jobs = list_outbox(limit=10)
    assert len(jobs) >= 2
