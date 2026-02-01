from fastapi import APIRouter, Depends

from service.api.models.wspci_models import GetPersonaRequest
from service.controllers.get_persona_controller import get_persona_controller
from service.controllers.request_wspci_access_token_controller import \
    generate_wspci_access_token
from service.utils.jwt_validator import verify_token
from service.utils.logger import logger

router = APIRouter()

@router.post("/wspci/token")
async def renew_wspci_access_token(jwt = Depends(verify_token)) -> dict:

    logger.info("Received request to generate WSPCI access token at /wspci/token")

    response_status = await generate_wspci_access_token()

    return response_status


@router.post("/wspci/persona")
async def get_persona(persona_data: GetPersonaRequest, jwt = Depends(verify_token)) -> dict:

    logger.info("Received request to query persona at /wspci/persona")

    persona_data = persona_data.model_dump()
    result = await get_persona_controller(persona_data)

    return result
