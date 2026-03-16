from fastapi import APIRouter

from service.controllers.request_access_token_controller import generate_afip_access_token
from service.controllers.request_wspci_access_token_controller import generate_wspci_access_token
from service.tenants.auth import verify_tenant
from service.tenants.billing import make_billing_dependency
from service.utils.logger import logger

router = APIRouter()


@router.post("/wsaa/token")
async def renew_access_token(billing=make_billing_dependency("wsaa_token")) -> dict:
    tenant = billing["tenant"]
    logger.info("Received request to generate WSAA access token for tenant %s", tenant["id"])
    return await generate_afip_access_token(tenant["id"])


@router.post("/wspci/token")
async def renew_wspci_access_token(billing=make_billing_dependency("wspci_token")) -> dict:
    tenant = billing["tenant"]
    logger.info("Received request to generate WSPCI access token for tenant %s", tenant["id"])
    return await generate_wspci_access_token(tenant["id"])
