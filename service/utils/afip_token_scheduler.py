import os
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from service.controllers.request_access_token_controller import \
    generate_afip_access_token
from service.controllers.request_wspci_access_token_controller import \
    generate_wspci_access_token
from service.caea_resilience.bootstrap import bootstrap_caea_cycles_once
from service.caea_resilience.outbox_worker import process_pending_outbox_jobs
from service.time.time_management import \
    generate_ntp_timestamp as time_provider
from service.utils.logger import logger
from service.xml_management.xml_builder import is_expiring_soon, xml_exists

scheduler = AsyncIOScheduler()

async def run_job():
    logger.info("Starting job: verifying WSFE token expiration")
    renew_before_minutes = int(os.getenv("WSFE_TOKEN_RENEW_BEFORE_MINUTES", "15"))

    if xml_exists("loginTicketResponse.xml") and not is_expiring_soon(
        "loginTicketResponse.xml",
        time_provider,
        renew_before_minutes=renew_before_minutes,
    ):
        logger.info("WSFE token still valid and not expiring soon. Job finished.")
        return

    token_generation_status = await generate_afip_access_token()

    if token_generation_status["status"] == "success":
        logger.info("WSFE token generated successfully. Job finished.")
    else:
        logger.info("Couldn't generate WSFE token by scheduler.")


async def run_wspci_job():
    logger.info("Starting job: verifying WSPCI token expiration")
    renew_before_minutes = int(os.getenv("WSPCI_TOKEN_RENEW_BEFORE_MINUTES", "15"))

    if xml_exists("wspci_loginTicketResponse.xml") and not is_expiring_soon(
        "wspci_loginTicketResponse.xml",
        time_provider,
        renew_before_minutes=renew_before_minutes,
    ):
        logger.info("WSPCI token still valid and not expiring soon. Job finished.")
        return

    token_generation_status = await generate_wspci_access_token()

    if token_generation_status["status"] == "success":
        logger.info("WSPCI token generated successfully. Job finished.")
    else:
        logger.info("Couldn't generate WSPCI token by scheduler.")


async def run_caea_outbox_job():
    logger.info("Starting job: processing CAEA outbox queue")
    result = await process_pending_outbox_jobs(limit=30)
    logger.info(
        "CAEA outbox job finished. processed=%s done=%s retried=%s failed=%s",
        result["processed"],
        result["done"],
        result["retried"],
        result["failed"],
    )


async def run_caea_bootstrap_job():
    logger.info("Starting job: ensuring CAEA cycles are preloaded")
    result = await bootstrap_caea_cycles_once()
    logger.info("CAEA bootstrap job finished: %s", result)


def start_scheduler():
    watchdog_minutes = int(os.getenv("AFIP_TOKEN_WATCHDOG_MINUTES", "5"))
    logger.info("Scheduler starting: token watchdog jobs configured every %s minutes", watchdog_minutes)

    scheduler.add_job(
        run_job,
        trigger="interval",
        minutes=watchdog_minutes,
        id="afip_token_watchdog",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        next_run_time=datetime.now(timezone.utc)
    )
    scheduler.add_job(
        run_wspci_job,
        trigger="interval",
        minutes=watchdog_minutes,
        id="afip_wspci_token_watchdog",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        next_run_time=datetime.now(timezone.utc)
    )
    scheduler.add_job(
        run_caea_outbox_job,
        trigger="interval",
        minutes=1,
        id="caea_outbox_watchdog",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        next_run_time=datetime.now(timezone.utc),
    )
    scheduler.add_job(
        run_caea_bootstrap_job,
        trigger="interval",
        hours=6,
        id="caea_bootstrap_watchdog",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        next_run_time=datetime.now(timezone.utc),
    )
    scheduler.start()   

def stop_scheduler():
    scheduler.shutdown(wait=False)
