from service.soap_client.async_client import WSPCIClientManager
from service.soap_client.wsdl.wsdl_manager import get_wspci_wsdl
from service.soap_client.wspci import consult_afip_wspci
from service.tenants.db import get_tenant_token
from service.utils.logger import logger

afip_wsdl = get_wspci_wsdl()


async def get_persona_controller(tenant_id: int, persona_data: dict) -> dict:
    logger.info("Querying persona idPersona=%s for tenant %s", persona_data["idPersona"], tenant_id)

    token_row = get_tenant_token(tenant_id, "wspci")
    if not token_row:
        return {"status": "error", "detail": "No WSPCI token found. Renew token first."}

    cuit_representada = persona_data["cuitRepresentada"]
    id_persona = persona_data["idPersona"]
    token = token_row["token"]
    sign = token_row["sign"]

    async def get_persona():
        manager = WSPCIClientManager(afip_wsdl)
        client = manager.get_client()
        return await client.service.getPersona(token, sign, cuit_representada, id_persona)

    return await consult_afip_wspci(get_persona, "getPersona")
