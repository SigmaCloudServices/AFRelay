"""
Authentication for AFRelay multitenant.

Two auth surfaces:
  1. Bearer token (API calls) → verify_tenant dependency
  2. Session (web portal) → require_admin / require_tenant_session
"""
import hashlib
import os
from typing import Optional

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from service.tenants.db import (check_password, get_tenant_by_api_key_hash,
                                 get_tenant_by_email, get_tenant_by_id)

_bearer = HTTPBearer()

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "ChangeMe1!")
ADMIN_API_KEY  = os.getenv("ADMIN_API_KEY",  "change-me-admin-api-key")


# ── REST API authentication ────────────────────────────────────────────────────

def verify_tenant(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> dict:
    """
    Resolve Bearer token → tenant record.
    Replaces the old static verify_token().
    """
    api_key_hash = hashlib.sha256(credentials.credentials.encode()).hexdigest()
    tenant = get_tenant_by_api_key_hash(api_key_hash)
    if not tenant:
        raise HTTPException(status_code=401, detail="Invalid API key")
    if not tenant["is_active"]:
        raise HTTPException(status_code=403, detail="Tenant account is inactive")
    return tenant


def verify_admin_api_key(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> bool:
    """Used by admin REST endpoints."""
    if credentials.credentials != ADMIN_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid admin API key")
    return True


# ── Web portal session authentication ─────────────────────────────────────────

class RequiresAdminLogin(Exception):
    pass


class RequiresTenantLogin(Exception):
    pass


def require_admin_session(request: Request) -> bool:
    """Raise if admin is not logged in via session."""
    if not request.session.get("admin_logged_in"):
        raise RequiresAdminLogin()
    return True


def require_tenant_session(request: Request) -> dict:
    """Return tenant dict if logged in via session, else raise."""
    tenant_id = request.session.get("tenant_id")
    if not tenant_id:
        raise RequiresTenantLogin()
    tenant = get_tenant_by_id(tenant_id)
    if not tenant or not tenant["is_active"]:
        request.session.clear()
        raise RequiresTenantLogin()
    return tenant


def get_current_tenant_or_none(request: Request) -> Optional[dict]:
    """Non-raising version — returns None if not logged in."""
    try:
        return require_tenant_session(request)
    except RequiresTenantLogin:
        return None


# ── Login helpers ──────────────────────────────────────────────────────────────

def login_admin(request: Request, username: str, password: str) -> bool:
    if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
        request.session["admin_logged_in"] = True
        return True
    return False


def login_tenant(request: Request, email: str, password: str) -> Optional[dict]:
    tenant = get_tenant_by_email(email)
    if not tenant:
        return None
    if not check_password(password, tenant["hashed_password"]):
        return None
    if not tenant["is_active"]:
        return None
    request.session["tenant_id"] = tenant["id"]
    return tenant


def logout_session(request: Request):
    request.session.clear()
