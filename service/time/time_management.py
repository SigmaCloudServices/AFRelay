import socket
from datetime import datetime, timedelta, timezone

import ntplib

from service.utils.logger import logger


def generate_ntp_timestamp() -> tuple[int, str, str]:

    logger.debug("Consulting NTP for get the datetime...")

    try:
        client = ntplib.NTPClient()
        response = client.request('time.afip.gov.ar', timeout=5)

    except socket.timeout:
        logger.warning("NTP request timed out")
        return False, False, False

    except Exception as e:
        logger.warning(f"NTP readiness check failed: {e}")
        return False, False, False

    generation_dt = datetime.fromtimestamp(response.tx_time, tz=timezone.utc)

    actual_time_epoch = int(generation_dt.timestamp())

    expiration_dte = generation_dt + timedelta(minutes=10)

    generation_time = generation_dt.strftime('%Y-%m-%dT%H:%M:%SZ')
    expiration_time = expiration_dte.strftime('%Y-%m-%dT%H:%M:%SZ')

    logger.debug(f"Datetime values: epoch: {actual_time_epoch} | gentime: {generation_time} | exptime: {expiration_time}")

    return actual_time_epoch, generation_time, expiration_time


def request_ntp_for_readiness() -> bool:
    try:
        logger.debug("Checking NTP availability for readiness...")
        client = ntplib.NTPClient()
        client.request("time.afip.gov.ar", timeout=5)
        return True
    
    except socket.timeout:
        logger.warning("NTP request timed out")
        return False
    
    except Exception as e:
        logger.warning(f"NTP readiness check failed: {e}")
        return False