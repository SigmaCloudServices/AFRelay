from service.payload_builder.builder import build_auth
from service.soap_client.async_client import WSFEClientManager
from service.soap_client.wsdl.wsdl_manager import get_wsfe_wsdl
from service.soap_client.wsfe import consult_afip_wsfe
from service.tenants.db import get_tenant_token
from service.utils.logger import logger

afip_wsdl = get_wsfe_wsdl()


async def consult_specific_invoice(tenant_id: int, comp_info: dict) -> dict:
    logger.info("Consulting invoice CbteNro=%s for tenant %s", comp_info["CbteNro"], tenant_id)

    token_row = get_tenant_token(tenant_id, "wsfe")
    if not token_row:
        return {"status": "error", "detail": "No WSFE token found. Renew token first."}

    auth = build_auth(token_row["token"], token_row["sign"], comp_info["Cuit"])
    fecomp_req = {
        "PtoVta": comp_info["PtoVta"],
        "CbteTipo": comp_info["CbteTipo"],
        "CbteNro": comp_info["CbteNro"],
    }

    async def fe_comp_consultar():
        manager = WSFEClientManager(afip_wsdl)
        client = manager.get_client()
        return await client.service.FECompConsultar(auth, fecomp_req)

    return await consult_afip_wsfe(fe_comp_consultar, "FECompConsultar")
