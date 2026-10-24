import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from httpx import AsyncClient

from service.api import app as app_module
from service.caea_resilience import db
from service.utils import afip_token_scheduler


@pytest.fixture
def isolated_state_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", Path(tmp_path / "s.db"))


@pytest.mark.asyncio
async def test_lifespan_does_not_wait_for_arca_bootstrap(isolated_state_db, override_auth, monkeypatch):
    bootstrap_started = []

    async def black_holed_bootstrap():
        bootstrap_started.append(1)
        await asyncio.sleep(30)

    # whichever name the lifespan might use, a bootstrap reaching ARCA would hang for 30 s
    monkeypatch.setattr(app_module, "bootstrap_caea_cycles_once", black_holed_bootstrap, raising=False)
    monkeypatch.setattr("service.caea_resilience.bootstrap.bootstrap_caea_cycles_once", black_holed_bootstrap)
    started = []
    monkeypatch.setattr(app_module, "start_scheduler", lambda: started.append(1))
    monkeypatch.setattr(app_module, "stop_scheduler", lambda: None)

    async def run():
        async with app_module.lifespan(app_module.app):
            async with AsyncClient(app=app_module.app, base_url="http://test") as client:
                assert (await client.get("/health/liveness")).status_code == 200
                assert (await client.get("/wsfe/caea/queue/outbox")).status_code == 200

    await asyncio.wait_for(run(), timeout=2)
    assert started == [1]
    assert bootstrap_started == []  # the scheduler's bootstrap job runs it, not the lifespan


def test_scheduler_runs_bootstrap_once_soon_after_start(monkeypatch):
    jobs = {}
    monkeypatch.setattr(afip_token_scheduler.scheduler, "add_job",
                        lambda func, **kw: jobs.__setitem__(kw["id"], (func, kw)))
    monkeypatch.setattr(afip_token_scheduler.scheduler, "start", lambda: None)
    afip_token_scheduler.start_scheduler()
    func, kw = jobs["caea_bootstrap_watchdog"]
    assert func is afip_token_scheduler.run_caea_bootstrap_job
    assert kw["max_instances"] == 1 and kw["coalesce"] is True
    assert kw["next_run_time"] <= datetime.now(timezone.utc) + timedelta(seconds=1)
