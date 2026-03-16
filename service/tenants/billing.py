"""
Billing layer for AFRelay multitenancy.

Provides:
  - make_billing_dependency(service_name) — FastAPI dependency factory
  - debit_after_call(tenant, service, price, reference) — post-call debit helper
"""
from fastapi import Depends, HTTPException

from service.tenants.auth import verify_tenant
from service.tenants.db import debit_balance, get_service_price


def make_billing_dependency(service_name: str):
    """
    Returns a FastAPI dependency that:
    1. Authenticates the tenant (via Bearer token)
    2. Checks they have sufficient balance
    3. Returns {tenant, service_name, price} for the route handler

    The route handler is responsible for calling debit_after_call() after
    the AFIP operation completes.
    """
    async def billing_dep(tenant: dict = Depends(verify_tenant)) -> dict:
        price = get_service_price(service_name)
        if price > 0 and tenant["balance"] < price:
            raise HTTPException(
                status_code=402,
                detail={
                    "error": "Insufficient balance",
                    "required": price,
                    "available": round(tenant["balance"], 4),
                    "service": service_name,
                },
            )
        return {"tenant": tenant, "service": service_name, "price": price}

    return Depends(billing_dep)


def debit_after_call(ctx: dict, reference: str = None) -> float:
    """
    Debit the tenant's balance after a successful (or AFIP-level) call.
    Always debits — even if AFIP returned an error — because the network
    round-trip was made.

    Returns the new balance.
    """
    tenant = ctx["tenant"]
    price = ctx["price"]
    service_name = ctx["service"]
    if price <= 0:
        return tenant["balance"]
    return debit_balance(tenant["id"], service_name, price, reference=reference)
