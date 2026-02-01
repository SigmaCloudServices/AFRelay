from zeep.helpers import serialize_object

from service.soap_client.wsfe import wsfe_dummy
from service.soap_client.wspci import wspci_dummy
from service.time.time_management import request_ntp_for_readiness
from service.utils.logger import logger


async def readiness_health_check() -> dict:
    logger.debug("Starting readiness health check")
    ntp = ""

    ntp_status = request_ntp_for_readiness()
    if ntp_status:
        ntp = "OK"
        logger.debug("NTP readiness check OK")

    else:
        ntp = {
            "status": "error",
            "message": "NTP query failed",
            "server": "time.afip.gov.ar"
        }
        logger.warning("NTP readiness check FAILED")

    # Check WSFE 
    wsfe_health_info = await wsfe_dummy()

    # Zeep returns an object of type '<class 'zeep.objects.[service response]'>'.
    # To work with the returned data, this object needs to be converted into a dictionary using serialize_object().
    wsfe_health_info_parsed = serialize_object(wsfe_health_info)
    logger.debug("WSFE dummy check OK")

    # Check WSPCI
    wspci_health_info = await wspci_dummy()
    wspci_health_info_parsed = serialize_object(wspci_health_info)
    logger.debug("WSPCI dummy check OK")

    logger.debug("Readiness health check finished")
    return {
        "ntp" : ntp,
        "wsfe_health" : wsfe_health_info_parsed,
        "wspci_health" : wspci_health_info_parsed
        }