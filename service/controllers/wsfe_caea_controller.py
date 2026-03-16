from service.payload_builder.builder import build_auth
from service.soap_client.async_client import WSFEClientManager
from service.soap_client.wsdl.wsdl_manager import get_wsfe_wsdl
from service.soap_client.wsfe import consult_afip_wsfe
from service.tenants.db import get_tenant_token
from service.utils.logger import logger

afip_wsdl = get_wsfe_wsdl()


async def _request_with_auth(tenant_id: int, method_name: str, cuit: int, *method_args) -> dict:
    token_row = get_tenant_token(tenant_id, "wsfe")
    if not token_row:
        return {"status": "error", "detail": "No WSFE token found. Renew token first."}

    auth = build_auth(token_row["token"], token_row["sign"], cuit)

    async def run():
        manager = WSFEClientManager(afip_wsdl)
        client = manager.get_client()
        return await getattr(client.service, method_name)(auth, *method_args)

    return await consult_afip_wsfe(run, method_name)


async def caea_solicitar(tenant_id: int, comp_info: dict) -> dict:
    logger.info("Requesting WSFE CAEA for tenant %s...", tenant_id)
    return await _request_with_auth(
        tenant_id,
        "FECAEASolicitar",
        comp_info["Cuit"],
        comp_info["Periodo"],
        comp_info["Orden"],
    )


async def caea_consultar(tenant_id: int, comp_info: dict) -> dict:
    logger.info("Consulting WSFE CAEA for tenant %s...", tenant_id)
    return await _request_with_auth(
        tenant_id,
        "FECAEAConsultar",
        comp_info["Cuit"],
        comp_info["Periodo"],
        comp_info["Orden"],
    )


async def caea_reg_informativo(tenant_id: int, comp_info: dict) -> dict:
    logger.info("Informing WSFE CAEA vouchers for tenant %s...", tenant_id)
    return await _request_with_auth(
        tenant_id,
        "FECAEARegInformativo",
        comp_info["Cuit"],
        comp_info["FeCAEARegInfReq"],
    )


async def caea_sin_movimiento_consultar(tenant_id: int, comp_info: dict) -> dict:
    logger.info("Consulting WSFE CAEA no-movement for tenant %s...", tenant_id)
    return await _request_with_auth(
        tenant_id,
        "FECAEASinMovimientoConsultar",
        comp_info["Cuit"],
        comp_info.get("CAEA"),
        comp_info["PtoVta"],
    )


async def caea_sin_movimiento_informar(tenant_id: int, comp_info: dict) -> dict:
    logger.info("Informing WSFE CAEA no-movement for tenant %s...", tenant_id)
    return await _request_with_auth(
        tenant_id,
        "FECAEASinMovimientoInformar",
        comp_info["Cuit"],
        comp_info["PtoVta"],
        comp_info["CAEA"],
    )
