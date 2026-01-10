from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from service.controllers.request_access_token_controller import \
    generate_afip_access_token
from service.time.time_management import \
    generate_ntp_timestamp as time_provider
from service.utils.logger import logger
from service.xml_management.xml_builder import is_expired, xml_exists

scheduler = AsyncIOScheduler()

async def run_job():
    logger.info("Starting job: verifying token expiration")

    if not xml_exists("loginTicketRequest.xml"):
        await generate_afip_access_token()
        return
    
    if xml_exists("loginTicketResponse.xml"):
        if is_expired("loginTicketResponse.xml", time_provider):
            await generate_afip_access_token()
            return
        
    if not xml_exists("loginTicketResponse.xml"):
        await generate_afip_access_token()
        return
        
    logger.info("Token is still valid. Job finished.")


def start_scheduler():
    logger.info("Scheduler starting: job configured to run every 11 hours")

    scheduler.add_job(
        run_job,
        trigger="interval",
        hours=11,
        id="afip_token_watchdog",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        next_run_time=datetime.now(timezone.utc)
    )
    scheduler.start()   

def stop_scheduler():
    scheduler.shutdown(wait=False)