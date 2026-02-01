from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from service.controllers.request_access_token_controller import \
    generate_afip_access_token
from service.controllers.request_wspci_access_token_controller import \
    generate_wspci_access_token
from service.time.time_management import \
    generate_ntp_timestamp as time_provider
from service.utils.logger import logger
from service.xml_management.xml_builder import is_expired, xml_exists

scheduler = AsyncIOScheduler()

async def run_job():
    logger.info("Starting job: verifying WSFE token expiration")

    if xml_exists("loginTicketResponse.xml") and not is_expired("loginTicketResponse.xml", time_provider):
        logger.info("WSFE token not expired. Job finished.")
        return

    token_generation_status = await generate_afip_access_token()

    if token_generation_status["status"] == "success":
        logger.info("WSFE token generated successfully. Job finished.")
    else:
        logger.info("Couldn't generate WSFE token by scheduler.")


async def run_wspci_job():
    logger.info("Starting job: verifying WSPCI token expiration")

    if xml_exists("wspci_loginTicketResponse.xml") and not is_expired("wspci_loginTicketResponse.xml", time_provider):
        logger.info("WSPCI token not expired. Job finished.")
        return

    token_generation_status = await generate_wspci_access_token()

    if token_generation_status["status"] == "success":
        logger.info("WSPCI token generated successfully. Job finished.")
    else:
        logger.info("Couldn't generate WSPCI token by scheduler.")


def start_scheduler():
    logger.info("Scheduler starting: jobs configured to run every 6 hours")

    scheduler.add_job(
        run_job,
        trigger="interval",
        hours=6,
        id="afip_token_watchdog",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        next_run_time=datetime.now(timezone.utc)
    )
    scheduler.add_job(
        run_wspci_job,
        trigger="interval",
        hours=6,
        id="afip_wspci_token_watchdog",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        next_run_time=datetime.now(timezone.utc)
    )
    scheduler.start()   

def stop_scheduler():
    scheduler.shutdown(wait=False)