import logging
from builtins import ConnectionResetError

import httpx
from tenacity import (before_sleep_log, retry, retry_if_exception_type,
                      stop_after_attempt, wait_fixed)
from zeep.exceptions import Fault, TransportError, XMLSyntaxError
from zeep.helpers import serialize_object

from service.soap_client.async_client import WSPCIClientManager
from service.soap_client.format_error import build_error_response
from service.soap_client.wsdl.wsdl_manager import get_wspci_wsdl
from service.utils.logger import logger


@retry(
        retry=retry_if_exception_type(( ConnectionResetError, httpx.ConnectError, TransportError )),
        stop=stop_after_attempt(3),
        wait=wait_fixed(0.5),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
async def consult_afip_wspci(make_request, METHOD: str) -> dict:

    try:
        afip_response = await make_request()
        logger.debug(f"Response: {afip_response}")

        afip_response = serialize_object(afip_response)

        return {
                "status" : "success",
                "response" : afip_response
                }

    except (httpx.ConnectError, httpx.TimeoutException) as e:
        return build_error_response(METHOD, "Network error", str(e))

    except TransportError as e:
        return build_error_response(METHOD, "HTTP Error", str(e))

    except Fault as e:
        logger.debug(f"SOAP FAULT in {METHOD}: {e}")
        return build_error_response(METHOD, "SOAPFault", str(e))

    except XMLSyntaxError as e:
        return build_error_response(METHOD, "Invalid AFIP response", str(e))

    except Exception as e:
        logger.error(f"General exception in {METHOD}: {e}")
        return build_error_response(METHOD, "unknown", str(e))


# ===================
# == HEALTH CHECK ===
# ===================

afip_wsdl = get_wspci_wsdl()

async def wspci_dummy():
    """
    WSPCI health check
    """
    logger.info(f"Consulting WSPCI dummy method (health check)...")
    manager = WSPCIClientManager(afip_wsdl)
    client = manager.get_client()
    try:
        health_info = await client.service.dummy()
        return health_info

    except Exception as e:
        logger.error(f"General exception in wspci_dummy: {e}")
        return health_info
