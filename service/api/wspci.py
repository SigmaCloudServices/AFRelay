from fastapi import APIRouter

from service.api.models.wspci_models import GetPersonaRequest
from service.controllers.get_persona_controller import get_persona_controller
from service.tenants.billing import debit_after_call, make_billing_dependency
from service.utils.logger import logger

router = APIRouter()


@router.post("/wspci/persona")
async def get_persona(
    persona_data: GetPersonaRequest,
    billing=make_billing_dependency("wspci_persona"),
) -> dict:
    tenant = billing["tenant"]
    logger.info("Received /wspci/persona for tenant %s", tenant["id"])
    result = await get_persona_controller(tenant["id"], persona_data.model_dump())
    debit_after_call(billing)
    return result
