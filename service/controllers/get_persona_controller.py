from service.soap_client.async_client import WSPCIClientManager
from service.soap_client.wsdl.wsdl_manager import get_wspci_wsdl
from service.soap_client.wspci import consult_afip_wspci
from service.utils.logger import logger
from service.xml_management.xml_builder import extract_wspci_token_and_sign_from_xml

afip_wsdl = get_wspci_wsdl()

async def get_persona_controller(persona_data: dict) -> dict:

    logger.info(f"Querying persona data for idPersona={persona_data['idPersona']}")

    token, sign = extract_wspci_token_and_sign_from_xml()

    cuit_representada = persona_data["cuitRepresentada"]
    id_persona = persona_data["idPersona"]

    async def get_persona():
        manager = WSPCIClientManager(afip_wsdl)
        client = manager.get_client()
        return await client.service.getPersona(token, sign, cuit_representada, id_persona)

    persona_result = await consult_afip_wspci(get_persona, "getPersona")
    return persona_result
