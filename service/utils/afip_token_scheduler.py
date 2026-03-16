import os
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from service.caea_resilience.bootstrap import bootstrap_caea_cycles_once
from service.caea_resilience.outbox_worker import process_pending_outbox_jobs
from service.controllers.request_access_token_controller import generate_afip_access_token
from service.controllers.request_wspci_access_token_controller import generate_wspci_access_token
from service.tenants.db import get_all_active_tenants, is_token_expiring_soon
from service.utils.logger import logger

scheduler = AsyncIOScheduler()


async def run_job():
    """Renew WSFE tokens for all active tenants."""
    renew_before_minutes = int(os.getenv("WSFE_TOKEN_RENEW_BEFORE_MINUTES", "15"))
    tenants = get_all_active_tenants()
    logger.info("Token watchdog: checking %d active tenants", len(tenants))

    for tenant in tenants:
        tid = tenant["id"]
        if not is_token_expiring_soon(tid, "wsfe", minutes=renew_before_minutes):
            logger.debug("WSFE token for tenant %s still valid, skipping.", tid)
            continue
        result = await generate_afip_access_token(tid)
        if result.get("status") == "success":
            logger.info("WSFE token renewed for tenant %s", tid)
        else:
            logger.warning("WSFE token renewal failed for tenant %s: %s", tid, result)


async def run_wspci_job():
    """Renew WSPCI tokens for tenants that have WSPCI certs."""
    renew_before_minutes = int(os.getenv("WSPCI_TOKEN_RENEW_BEFORE_MINUTES", "15"))
    tenants = get_all_active_tenants()

    for tenant in tenants:
        tid = tenant["id"]
        if not is_token_expiring_soon(tid, "wspci", minutes=renew_before_minutes):
            continue
        result = await generate_wspci_access_token(tid)
        if result.get("status") == "success":
            logger.info("WSPCI token renewed for tenant %s", tid)
        else:
            logger.debug("WSPCI token renewal skipped/failed for tenant %s: %s", tid, result)


async def run_caea_outbox_job():
    logger.info("Starting job: processing CAEA outbox queue")
    result = await process_pending_outbox_jobs(limit=30)
    logger.info(
        "CAEA outbox job finished. processed=%s done=%s retried=%s failed=%s",
        result["processed"], result["done"], result["retried"], result["failed"],
    )


async def run_caea_bootstrap_job():
    logger.info("Starting job: ensuring CAEA cycles are preloaded")
    result = await bootstrap_caea_cycles_once()
    logger.info("CAEA bootstrap job finished: %s", result)


def start_scheduler():
    watchdog_minutes = int(os.getenv("AFIP_TOKEN_WATCHDOG_MINUTES", "5"))
    logger.info("Scheduler starting: token watchdog every %s minutes", watchdog_minutes)

    for job_id, func, interval, unit in [
        ("afip_token_watchdog",       run_job,                 watchdog_minutes, "minutes"),
        ("afip_wspci_token_watchdog", run_wspci_job,           watchdog_minutes, "minutes"),
        ("caea_outbox_watchdog",      run_caea_outbox_job,     1,                "minutes"),
        ("caea_bootstrap_watchdog",   run_caea_bootstrap_job,  6,                "hours"),
    ]:
        scheduler.add_job(
            func,
            trigger="interval",
            **{unit: interval},
            id=job_id,
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            next_run_time=datetime.now(timezone.utc),
        )

    scheduler.start()


def stop_scheduler():
    scheduler.shutdown(wait=False)
