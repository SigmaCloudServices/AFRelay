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


async def caea_solicitar(comp_info: dict) -> dict:
    logger.info("Requesting WSFE CAEA...")
    return await _request_with_auth(
        "FECAEASolicitar",
        comp_info["Cuit"],
        comp_info["Periodo"],
        comp_info["Orden"],
    )


async def caea_consultar(comp_info: dict) -> dict:
    logger.info("Consulting WSFE CAEA...")
    return await _request_with_auth(
        "FECAEAConsultar",
        comp_info["Cuit"],
        comp_info["Periodo"],
        comp_info["Orden"],
    )


async def caea_reg_informativo(comp_info: dict) -> dict:
    logger.info("Informing WSFE CAEA vouchers...")
    return await _request_with_auth(
        "FECAEARegInformativo",
        comp_info["Cuit"],
        comp_info["FeCAEARegInfReq"],
    )


async def caea_sin_movimiento_consultar(comp_info: dict) -> dict:
    logger.info("Consulting WSFE CAEA no-movement statement...")
    return await _request_with_auth(
        "FECAEASinMovimientoConsultar",
        comp_info["Cuit"],
        comp_info.get("CAEA"),
        comp_info["PtoVta"],
    )


async def caea_sin_movimiento_informar(comp_info: dict) -> dict:
    logger.info("Informing WSFE CAEA no-movement statement...")
    return await _request_with_auth(
        "FECAEASinMovimientoInformar",
        comp_info["Cuit"],
        comp_info["PtoVta"],
        comp_info["CAEA"],
    )
