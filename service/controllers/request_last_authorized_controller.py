from service.payload_builder.builder import build_auth
from service.soap_client.async_client import WSFEClientManager
from service.soap_client.wsdl.wsdl_manager import get_wsfe_wsdl
from service.soap_client.wsfe import consult_afip_wsfe
from service.tenants.db import get_tenant_token
from service.utils.logger import logger

afip_wsdl = get_wsfe_wsdl()


async def get_last_authorized_info(tenant_id: int, comp_info: dict) -> dict:
    logger.info("Consulting last authorized invoice for tenant %s", tenant_id)

    token_row = get_tenant_token(tenant_id, "wsfe")
    if not token_row:
        return {"status": "error", "detail": "No WSFE token found. Renew token first."}

    auth = build_auth(token_row["token"], token_row["sign"], comp_info["Cuit"])

    async def fe_comp_ultimo_autorizado():
        manager = WSFEClientManager(afip_wsdl)
        client = manager.get_client()
        return await client.service.FECompUltimoAutorizado(
            auth, comp_info["PtoVta"], comp_info["CbteTipo"]
        )

    return await consult_afip_wsfe(fe_comp_ultimo_autorizado, "FECompUltimoAutorizado")
