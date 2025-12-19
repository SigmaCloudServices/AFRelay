from service.soap_management.soap_client import wsfe_dummy
from service.time.time_management import generate_ntp_timestamp
from service.utils.convert_to_dict import convert_zeep_object_to_dict


def readiness_health_check() -> dict:

    ntp = ""

    actual_time_epoch, generation_time, expiration_time = generate_ntp_timestamp()
    if actual_time_epoch and generation_time and expiration_time:
        ntp = "OK"

    else:
        ntp = {
            "status": "error",
            "message": "NTP query failed",
            "server": "time.afip.gov.ar"
        }

    # Check WSFE
    wsfe_health_info = wsfe_dummy()
    wsfe_health_info_parsed = convert_zeep_object_to_dict(wsfe_health_info)

    return {
        "ntp" : ntp,
        "wsfe_health" : wsfe_health_info_parsed
        }