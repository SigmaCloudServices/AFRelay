"""
REST Admin API — protected by admin API key (Bearer).
Provides tenant CRUD, balance management, and service pricing.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from service.tenants.auth import verify_admin_api_key
from service.tenants.db import (
    activate_cert, create_tenant, credit_balance, get_all_active_tenants,
    get_tenant_by_id, list_service_prices, list_tenant_certs,
    list_transactions, update_service_price, update_tenant,
)
from service.utils.logger import logger

router = APIRouter(prefix="/admin", dependencies=[Depends(verify_admin_api_key)])


# ── Tenant management ─────────────────────────────────────────────────────────

class CreateTenantRequest(BaseModel):
    name: str
    email: str
    password: str
    cuit: str
    notes: str = ""


@router.get("/tenants")
def list_tenants_endpoint() -> dict:
    tenants = get_all_active_tenants()
    return {"tenants": tenants, "count": len(tenants)}


@router.post("/tenants")
def create_tenant_endpoint(req: CreateTenantRequest) -> dict:
    try:
        tenant, plain_api_key = create_tenant(
            name=req.name,
            email=req.email,
            password=req.password,
            cuit=req.cuit,
            notes=req.notes,
        )
        logger.info("Admin created tenant id=%s name=%s", tenant["id"], tenant["name"])
        return {"tenant": tenant, "api_key": plain_api_key}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/tenants/{tenant_id}")
def get_tenant(tenant_id: int) -> dict:
    tenant = get_tenant_by_id(tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return {"tenant": tenant}


@router.post("/tenants/{tenant_id}/deactivate")
def deactivate(tenant_id: int) -> dict:
    update_tenant(tenant_id, is_active=0)
    return {"status": "deactivated", "tenant_id": tenant_id}


@router.post("/tenants/{tenant_id}/reactivate")
def reactivate(tenant_id: int) -> dict:
    update_tenant(tenant_id, is_active=1)
    return {"status": "reactivated", "tenant_id": tenant_id}


# ── Balance management ────────────────────────────────────────────────────────

class CreditRequest(BaseModel):
    amount: float
    reference: str = ""


@router.post("/tenants/{tenant_id}/credit")
def credit_tenant(tenant_id: int, req: CreditRequest) -> dict:
    if req.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")
    new_balance = credit_balance(tenant_id, req.amount, reference=req.reference or None)
    logger.info("Credited %.4f to tenant %s, new balance=%.4f", req.amount, tenant_id, new_balance)
    return {"status": "credited", "amount": req.amount, "new_balance": new_balance}


@router.get("/tenants/{tenant_id}/transactions")
def tenant_transactions(tenant_id: int, limit: int = 100) -> dict:
    rows = list_transactions(tenant_id, limit=limit)
    return {"transactions": rows, "count": len(rows)}


@router.get("/tenants/{tenant_id}/certs")
def tenant_certs_endpoint(tenant_id: int) -> dict:
    rows = list_tenant_certs(tenant_id)
    for r in rows:
        r.pop("private_key_encrypted", None)
    return {"certs": rows, "count": len(rows)}


@router.post("/tenants/{tenant_id}/certs/{cert_id}/activate")
def activate_tenant_cert(tenant_id: int, cert_id: int) -> dict:
    activate_cert(cert_id)
    return {"status": "activated", "cert_id": cert_id}


# ── Service pricing ───────────────────────────────────────────────────────────

class UpdatePriceRequest(BaseModel):
    price: float


@router.get("/prices")
def list_prices() -> dict:
    prices = list_service_prices()
    return {"prices": prices}


@router.put("/prices/{service_name}")
def update_price(service_name: str, req: UpdatePriceRequest) -> dict:
    if req.price < 0:
        raise HTTPException(status_code=400, detail="Price cannot be negative")
    updated = update_service_price(service_name, req.price)
    if not updated:
        raise HTTPException(status_code=404, detail=f"Service '{service_name}' not found")
    logger.info("Admin updated price for %s → %.4f", service_name, req.price)
    return {"status": "updated", "service": service_name, "price": req.price}
