from service.payload_builder.builder import build_auth
from service.soap_client.async_client import WSFEClientManager
from service.soap_client.wsdl.wsdl_manager import get_wsfe_wsdl
from service.soap_client.wsfe import consult_afip_wsfe
from service.utils.logger import logger
from service.xml_management.xml_builder import extract_token_and_sign_from_xml

afip_wsdl = get_wsfe_wsdl()


async def _request_with_auth(method_name: str, cuit: int, *method_args) -> dict:
    token, sign = extract_token_and_sign_from_xml()
    auth = build_auth(token, sign, cuit)

    async def run():
        manager = WSFEClientManager(afip_wsdl)
        client = manager.get_client()
        return await getattr(client.service, method_name)(auth, *method_args)

    return await consult_afip_wsfe(run, method_name)


async def get_max_records_per_request(comp_info: dict) -> dict:
    logger.info("Consulting max records per WSFE request...")
    return await _request_with_auth("FECompTotXRequest", comp_info["Cuit"])


async def get_types_cbte(comp_info: dict) -> dict:
    logger.info("Consulting WSFE voucher types...")
    return await _request_with_auth("FEParamGetTiposCbte", comp_info["Cuit"])


async def get_types_doc(comp_info: dict) -> dict:
    logger.info("Consulting WSFE document types...")
    return await _request_with_auth("FEParamGetTiposDoc", comp_info["Cuit"])


async def get_types_iva(comp_info: dict) -> dict:
    logger.info("Consulting WSFE VAT types...")
    return await _request_with_auth("FEParamGetTiposIva", comp_info["Cuit"])


async def get_types_tributos(comp_info: dict) -> dict:
    logger.info("Consulting WSFE tributo types...")
    return await _request_with_auth("FEParamGetTiposTributos", comp_info["Cuit"])


async def get_types_monedas(comp_info: dict) -> dict:
    logger.info("Consulting WSFE currency types...")
    return await _request_with_auth("FEParamGetTiposMonedas", comp_info["Cuit"])


async def get_condicion_iva_receptor(comp_info: dict) -> dict:
    logger.info("Consulting WSFE receptor VAT conditions...")
    return await _request_with_auth(
        "FEParamGetCondicionIvaReceptor",
        comp_info["Cuit"],
        comp_info.get("ClaseCmp"),
    )


async def get_puntos_venta(comp_info: dict) -> dict:
    logger.info("Consulting WSFE sale points...")
    return await _request_with_auth("FEParamGetPtosVenta", comp_info["Cuit"])


async def get_cotizacion(comp_info: dict) -> dict:
    logger.info("Consulting WSFE currency quote...")
    return await _request_with_auth(
        "FEParamGetCotizacion",
        comp_info["Cuit"],
        comp_info["MonId"],
        comp_info.get("FchCotiz"),
    )


async def get_types_concepto(comp_info: dict) -> dict:
    logger.info("Consulting WSFE concept types...")
    return await _request_with_auth("FEParamGetTiposConcepto", comp_info["Cuit"])


async def get_types_opcional(comp_info: dict) -> dict:
    logger.info("Consulting WSFE optional types...")
    return await _request_with_auth("FEParamGetTiposOpcional", comp_info["Cuit"])


async def get_types_paises(comp_info: dict) -> dict:
    logger.info("Consulting WSFE country types...")
    return await _request_with_auth("FEParamGetTiposPaises", comp_info["Cuit"])


async def get_actividades(comp_info: dict) -> dict:
    logger.info("Consulting WSFE issuer activities...")
    return await _request_with_auth("FEParamGetActividades", comp_info["Cuit"])
