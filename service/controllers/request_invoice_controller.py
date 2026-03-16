from service.payload_builder.builder import add_auth_to_payload
from service.soap_client.async_client import WSFEClientManager
from service.soap_client.wsdl.wsdl_manager import get_wsfe_wsdl
from service.soap_client.wsfe import consult_afip_wsfe
from service.tenants.db import get_tenant_token
from service.utils.logger import logger

afip_wsdl = get_wsfe_wsdl()


async def request_invoice_controller(tenant_id: int, sale_data: dict) -> dict:
    logger.info("Generating invoice for tenant %s...", tenant_id)

    token_row = get_tenant_token(tenant_id, "wsfe")
    if not token_row:
        return {"status": "error", "detail": "No WSFE token found. Renew token first."}

    invoice_with_auth = add_auth_to_payload(sale_data, token_row["token"], token_row["sign"])

    async def fecae_solicitar():
        manager = WSFEClientManager(afip_wsdl)
        client = manager.get_client()
        return await client.service.FECAESolicitar(
            invoice_with_auth["Auth"], invoice_with_auth["FeCAEReq"]
        )

    return await consult_afip_wsfe(fecae_solicitar, "FECAESolicitar")
