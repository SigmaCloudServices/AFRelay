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


async def get_max_records_per_request(tenant_id: int, comp_info: dict) -> dict:
    logger.info("Consulting max records per WSFE request...")
    return await _request_with_auth(tenant_id, "FECompTotXRequest", comp_info["Cuit"])


async def get_types_cbte(tenant_id: int, comp_info: dict) -> dict:
    logger.info("Consulting WSFE voucher types...")
    return await _request_with_auth(tenant_id, "FEParamGetTiposCbte", comp_info["Cuit"])


async def get_types_doc(tenant_id: int, comp_info: dict) -> dict:
    logger.info("Consulting WSFE document types...")
    return await _request_with_auth(tenant_id, "FEParamGetTiposDoc", comp_info["Cuit"])


async def get_types_iva(tenant_id: int, comp_info: dict) -> dict:
    logger.info("Consulting WSFE VAT types...")
    return await _request_with_auth(tenant_id, "FEParamGetTiposIva", comp_info["Cuit"])


async def get_types_tributos(tenant_id: int, comp_info: dict) -> dict:
    logger.info("Consulting WSFE tributo types...")
    return await _request_with_auth(tenant_id, "FEParamGetTiposTributos", comp_info["Cuit"])


async def get_types_monedas(tenant_id: int, comp_info: dict) -> dict:
    logger.info("Consulting WSFE currency types...")
    return await _request_with_auth(tenant_id, "FEParamGetTiposMonedas", comp_info["Cuit"])


async def get_condicion_iva_receptor(tenant_id: int, comp_info: dict) -> dict:
    logger.info("Consulting WSFE receptor VAT conditions...")
    return await _request_with_auth(
        tenant_id,
        "FEParamGetCondicionIvaReceptor",
        comp_info["Cuit"],
        comp_info.get("ClaseCmp"),
    )


async def get_puntos_venta(tenant_id: int, comp_info: dict) -> dict:
    logger.info("Consulting WSFE sale points...")
    return await _request_with_auth(tenant_id, "FEParamGetPtosVenta", comp_info["Cuit"])


async def get_cotizacion(tenant_id: int, comp_info: dict) -> dict:
    logger.info("Consulting WSFE currency quote...")
    return await _request_with_auth(
        tenant_id,
        "FEParamGetCotizacion",
        comp_info["Cuit"],
        comp_info["MonId"],
        comp_info.get("FchCotiz"),
    )


async def get_types_concepto(tenant_id: int, comp_info: dict) -> dict:
    logger.info("Consulting WSFE concept types...")
    return await _request_with_auth(tenant_id, "FEParamGetTiposConcepto", comp_info["Cuit"])


async def get_types_opcional(tenant_id: int, comp_info: dict) -> dict:
    logger.info("Consulting WSFE optional types...")
    return await _request_with_auth(tenant_id, "FEParamGetTiposOpcional", comp_info["Cuit"])


async def get_types_paises(tenant_id: int, comp_info: dict) -> dict:
    logger.info("Consulting WSFE country types...")
    return await _request_with_auth(tenant_id, "FEParamGetTiposPaises", comp_info["Cuit"])


async def get_actividades(tenant_id: int, comp_info: dict) -> dict:
    logger.info("Consulting WSFE issuer activities...")
    return await _request_with_auth(tenant_id, "FEParamGetActividades", comp_info["Cuit"])
