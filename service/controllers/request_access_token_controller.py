from lxml import etree

from service.observability.collector import emit_domain_event
from service.crypto.sign import sign_login_ticket_request
from service.soap_client.async_client import wsaa_client
from service.soap_client.wsaa import consult_afip_wsaa
from service.soap_client.wsdl.wsdl_manager import get_wsaa_wsdl
from service.tenants.cert_manager import get_cert_bytes_for_tenant
from service.tenants.db import save_tenant_token
from service.time.time_management import generate_ntp_timestamp
from service.utils.logger import logger
from service.xml_management.xml_builder import build_login_ticket_request


def _parse_token_response(login_ticket_response_xml: str) -> tuple[str, str, str]:
    """Extract (token, sign, expires_at) from WSAA loginTicketResponse XML."""
    root = etree.fromstring(login_ticket_response_xml.encode("utf-8"))
    token = root.find(".//token").text
    sign = root.find(".//sign").text
    expiration_elem = root.find(".//expirationTime")
    expires_at = expiration_elem.text if expiration_elem is not None else ""
    return token, sign, expires_at


async def generate_afip_access_token(tenant_id: int) -> dict:
    logger.info("Generating new WSFE access token for tenant %s", tenant_id)
    emit_domain_event(
        event_type="token_renewal", service="wsaa",
        status="started", entity_key=f"tenant:{tenant_id}:wsfe",
    )

    try:
        cert_bytes, key_bytes = get_cert_bytes_for_tenant(tenant_id, "wsfe")
    except RuntimeError as e:
        logger.error("Cert error for tenant %s: %s", tenant_id, e)
        emit_domain_event(event_type="token_renewal", service="wsaa",
                          status="error", entity_key=f"tenant:{tenant_id}:wsfe",
                          error_type="cert_missing")
        return {"status": "error", "detail": str(e)}

    root = build_login_ticket_request(generate_ntp_timestamp, service_name="wsfe")
    from lxml import etree as _et
    request_bytes = _et.tostring(root, xml_declaration=True, encoding="UTF-8")
    b64_cms = sign_login_ticket_request(request_bytes, key_bytes, cert_bytes)

    afip_wsdl = get_wsaa_wsdl()
    client, httpx_client = wsaa_client(afip_wsdl)

    async def login_cms():
        try:
            return await client.service.loginCms(b64_cms)
        finally:
            if client and client.transport:
                await client.transport.aclose()
            else:
                await httpx_client.aclose()

    login_ticket_response = await consult_afip_wsaa(login_cms, "loginCms")

    if login_ticket_response["status"] == "success":
        token, sign, expires_at = _parse_token_response(login_ticket_response["response"])
        save_tenant_token(tenant_id, "wsfe", token, sign, expires_at)
        emit_domain_event(event_type="token_renewal", service="wsaa",
                          status="success", entity_key=f"tenant:{tenant_id}:wsfe")
        logger.info("WSFE token generated for tenant %s (expires %s)", tenant_id, expires_at)
        return {"status": "success"}
    else:
        logger.error("Failed to generate WSFE token for tenant %s", tenant_id)
        emit_domain_event(event_type="token_renewal", service="wsaa",
                          status="error", entity_key=f"tenant:{tenant_id}:wsfe",
                          error_type="token_generation_failed")
        return {"status": "error", "detail": "WSAA call failed"}
