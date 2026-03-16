"""
HTML Portal routes for AFRelay multitenancy.
- /portal/admin/* — Admin session portal
- /portal/* — Tenant session portal
"""
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from service.caea_resilience import repository as caea_repo
from service.caea_resilience.db import init_db
from service.caea_resilience.outbox_worker import process_pending_outbox_jobs
from service.tenants.auth import (
    RequiresAdminLogin, RequiresTenantLogin,
    login_admin, login_tenant, logout_session,
    require_admin_session, require_tenant_session,
)
from service.tenants.cert_manager import generate_key_and_csr, validate_cert_pem
from service.tenants.db import (
    activate_cert, check_password, create_cert_record, create_tenant,
    get_admin_stats, get_all_active_tenants, get_cert_by_id, get_tenant_by_id,
    get_tenant_token, is_token_expired, list_service_prices, list_tenant_certs,
    list_transactions, rotate_api_key, update_password, update_service_price,
    update_tenant, upload_cert, credit_balance,
)
from service.utils.logger import logger

router = APIRouter(prefix="/portal")

import os
_TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ui", "templates")
templates = Jinja2Templates(directory=_TEMPLATE_DIR)


def _flash(category: str, message: str) -> dict:
    return {"category": category, "message": message}


def _redirect_with_flash(url: str) -> RedirectResponse:
    return RedirectResponse(url=url, status_code=303)


# ── Admin Login ────────────────────────────────────────────────────────────────

@router.get("/admin/login", response_class=HTMLResponse)
def admin_login_page(request: Request, error: str = None):
    return templates.TemplateResponse("login.html", {
        "request": request,
        "is_admin": True,
        "action_url": "/portal/admin/login",
        "error": error,
    })


@router.post("/admin/login")
def admin_login_submit(request: Request, username: str = Form(...), password: str = Form(...)):
    if login_admin(request, username, password):
        return RedirectResponse(url="/portal/admin/dashboard", status_code=303)
    return templates.TemplateResponse("login.html", {
        "request": request,
        "is_admin": True,
        "action_url": "/portal/admin/login",
        "error": "Usuario o contraseña incorrectos.",
    })


@router.get("/admin/logout")
def admin_logout(request: Request):
    logout_session(request)
    return RedirectResponse(url="/portal/admin/login", status_code=303)


# ── Admin Dashboard ────────────────────────────────────────────────────────────

@router.get("/admin/dashboard", response_class=HTMLResponse)
def admin_dashboard(request: Request):
    try:
        require_admin_session(request)
    except RequiresAdminLogin:
        return RedirectResponse(url="/portal/admin/login", status_code=303)

    stats = get_admin_stats()
    tenants = get_all_active_tenants()[:10]
    prices = list_service_prices()
    return templates.TemplateResponse("admin/dashboard.html", {
        "request": request, "active": "dashboard",
        "admin_user": "Admin",
        "stats": stats, "tenants": tenants, "prices": prices,
        "flash": request.session.pop("flash", None),
    })


# ── Admin Tenants ──────────────────────────────────────────────────────────────

@router.get("/admin/tenants", response_class=HTMLResponse)
def admin_tenants(request: Request):
    try:
        require_admin_session(request)
    except RequiresAdminLogin:
        return RedirectResponse(url="/portal/admin/login", status_code=303)

    tenants = get_all_active_tenants()
    return templates.TemplateResponse("admin/tenants.html", {
        "request": request, "active": "tenants",
        "admin_user": "Admin", "tenants": tenants,
        "flash": request.session.pop("flash", None),
    })


@router.post("/admin/tenants/create")
def admin_create_tenant(
    request: Request,
    name: str = Form(...), email: str = Form(...),
    password: str = Form(...), cuit: str = Form(...),
    notes: str = Form(default=""),
):
    try:
        require_admin_session(request)
    except RequiresAdminLogin:
        return RedirectResponse(url="/portal/admin/login", status_code=303)

    try:
        tenant, plain_key = create_tenant(name=name, email=email, password=password, cuit=cuit, notes=notes)
        request.session["flash"] = _flash("success", f"Tenant creado. API Key: {plain_key}")
        request.session["new_api_key_for_tenant"] = {
            "tenant_id": tenant["id"], "api_key": plain_key
        }
        return RedirectResponse(url=f"/portal/admin/tenants/{tenant['id']}", status_code=303)
    except Exception as e:
        request.session["flash"] = _flash("danger", f"Error: {e}")
        return RedirectResponse(url="/portal/admin/tenants", status_code=303)


@router.get("/admin/tenants/{tenant_id}", response_class=HTMLResponse)
def admin_tenant_detail(request: Request, tenant_id: int):
    try:
        require_admin_session(request)
    except RequiresAdminLogin:
        return RedirectResponse(url="/portal/admin/login", status_code=303)

    tenant = get_tenant_by_id(tenant_id)
    if not tenant:
        return RedirectResponse(url="/portal/admin/tenants", status_code=303)

    certs = list_tenant_certs(tenant_id)
    for c in certs:
        c.pop("private_key_encrypted", None)
    transactions = list_transactions(tenant_id, limit=20)

    new_api_key_data = request.session.pop("new_api_key_for_tenant", None)
    new_api_key = None
    if new_api_key_data and new_api_key_data.get("tenant_id") == tenant_id:
        new_api_key = new_api_key_data.get("api_key")

    return templates.TemplateResponse("admin/tenant_detail.html", {
        "request": request, "active": "tenants",
        "admin_user": "Admin", "tenant": tenant,
        "certs": certs, "transactions": transactions,
        "new_api_key": new_api_key,
        "flash": request.session.pop("flash", None),
    })


@router.post("/admin/tenants/{tenant_id}/credit")
def admin_credit(
    request: Request, tenant_id: int,
    amount: float = Form(...), reference: str = Form(default=""),
):
    try:
        require_admin_session(request)
    except RequiresAdminLogin:
        return RedirectResponse(url="/portal/admin/login", status_code=303)

    if amount > 0:
        credit_balance(tenant_id, amount, reference=reference or None)
        request.session["flash"] = _flash("success", f"${amount:.4f} acreditados correctamente.")
    return RedirectResponse(url=f"/portal/admin/tenants/{tenant_id}", status_code=303)


@router.post("/admin/tenants/{tenant_id}/deactivate")
def admin_deactivate(request: Request, tenant_id: int):
    try:
        require_admin_session(request)
    except RequiresAdminLogin:
        return RedirectResponse(url="/portal/admin/login", status_code=303)
    update_tenant(tenant_id, is_active=0)
    request.session["flash"] = _flash("warning", "Tenant desactivado.")
    return RedirectResponse(url=f"/portal/admin/tenants/{tenant_id}", status_code=303)


@router.post("/admin/tenants/{tenant_id}/reactivate")
def admin_reactivate(request: Request, tenant_id: int):
    try:
        require_admin_session(request)
    except RequiresAdminLogin:
        return RedirectResponse(url="/portal/admin/login", status_code=303)
    update_tenant(tenant_id, is_active=1)
    request.session["flash"] = _flash("success", "Tenant reactivado.")
    return RedirectResponse(url=f"/portal/admin/tenants/{tenant_id}", status_code=303)


@router.post("/admin/tenants/{tenant_id}/rotate-key")
def admin_rotate_key(request: Request, tenant_id: int):
    try:
        require_admin_session(request)
    except RequiresAdminLogin:
        return RedirectResponse(url="/portal/admin/login", status_code=303)
    _, plain_key = rotate_api_key(tenant_id)
    request.session["new_api_key_for_tenant"] = {"tenant_id": tenant_id, "api_key": plain_key}
    return RedirectResponse(url=f"/portal/admin/tenants/{tenant_id}", status_code=303)


# ── Admin Certs ────────────────────────────────────────────────────────────────

@router.get("/admin/tenants/{tenant_id}/certs", response_class=HTMLResponse)
def admin_tenant_certs(request: Request, tenant_id: int):
    try:
        require_admin_session(request)
    except RequiresAdminLogin:
        return RedirectResponse(url="/portal/admin/login", status_code=303)

    tenant = get_tenant_by_id(tenant_id)
    certs = list_tenant_certs(tenant_id)
    for c in certs:
        c.pop("private_key_encrypted", None)
    pending_cert = next((c for c in certs if c["status"] == "pending_cert"), None)
    new_csr = request.session.pop("new_csr", None)
    return templates.TemplateResponse("admin/tenant_certs.html", {
        "request": request, "active": "tenants",
        "admin_user": "Admin", "tenant": tenant,
        "certs": certs, "pending_cert": pending_cert,
        "new_csr": new_csr,
        "flash": request.session.pop("flash", None),
    })


@router.post("/admin/tenants/{tenant_id}/certs/generate-csr")
def admin_generate_csr(
    request: Request, tenant_id: int,
    service: str = Form(...), common_name: str = Form(...),
    organization: str = Form(...), country: str = Form(default="AR"),
    cuit: str = Form(...),
):
    try:
        require_admin_session(request)
    except RequiresAdminLogin:
        return RedirectResponse(url="/portal/admin/login", status_code=303)

    _, csr_pem, encrypted_key = generate_key_and_csr(
        common_name=common_name, organization=organization,
        cuit=cuit, country=country,
    )
    create_cert_record(
        tenant_id=tenant_id, service=service,
        common_name=common_name, organization=organization,
        country=country, cuit=cuit,
        private_key_encrypted=encrypted_key, csr_pem=csr_pem,
    )
    request.session["new_csr"] = csr_pem
    request.session["flash"] = _flash("success", f"CSR generado para {service}. Envialo a AFIP.")
    return RedirectResponse(url=f"/portal/admin/tenants/{tenant_id}/certs", status_code=303)


@router.post("/admin/tenants/{tenant_id}/certs/{cert_id}/upload")
def admin_upload_cert(
    request: Request, tenant_id: int, cert_id: int,
    cert_pem: str = Form(...),
):
    try:
        require_admin_session(request)
    except RequiresAdminLogin:
        return RedirectResponse(url="/portal/admin/login", status_code=303)

    valid, msg = validate_cert_pem(cert_pem)
    if not valid:
        request.session["flash"] = _flash("danger", f"Certificado inválido: {msg}")
        return RedirectResponse(url=f"/portal/admin/tenants/{tenant_id}/certs", status_code=303)

    upload_cert(cert_id, cert_pem.strip())
    activate_cert(cert_id)
    request.session["flash"] = _flash("success", "Certificado cargado y activado.")
    return RedirectResponse(url=f"/portal/admin/tenants/{tenant_id}/certs", status_code=303)


@router.post("/admin/tenants/{tenant_id}/certs/{cert_id}/activate")
def admin_activate_cert(request: Request, tenant_id: int, cert_id: int):
    try:
        require_admin_session(request)
    except RequiresAdminLogin:
        return RedirectResponse(url="/portal/admin/login", status_code=303)
    activate_cert(cert_id)
    return RedirectResponse(url=f"/portal/admin/tenants/{tenant_id}/certs", status_code=303)


# ── Admin Prices ───────────────────────────────────────────────────────────────

@router.get("/admin/prices", response_class=HTMLResponse)
def admin_prices(request: Request):
    try:
        require_admin_session(request)
    except RequiresAdminLogin:
        return RedirectResponse(url="/portal/admin/login", status_code=303)

    prices = list_service_prices()
    return templates.TemplateResponse("admin/prices.html", {
        "request": request, "active": "prices",
        "admin_user": "Admin", "prices": prices,
        "flash": request.session.pop("flash", None),
    })


@router.post("/admin/prices/update")
async def admin_update_prices(request: Request):
    try:
        require_admin_session(request)
    except RequiresAdminLogin:
        return RedirectResponse(url="/portal/admin/login", status_code=303)

    form = await request.form()
    for key, value in form.items():
        if key.startswith("price_"):
            service_name = key[6:]
            try:
                update_service_price(service_name, float(value))
            except (ValueError, Exception):
                pass
    request.session["flash"] = _flash("success", "Precios actualizados.")
    return RedirectResponse(url="/portal/admin/prices", status_code=303)


# ── Admin Monitoring ───────────────────────────────────────────────────────────

@router.get("/admin/monitoring", response_class=HTMLResponse)
def admin_monitoring(request: Request):
    try:
        require_admin_session(request)
    except RequiresAdminLogin:
        return RedirectResponse(url="/portal/admin/login", status_code=303)

    init_db()
    tenants = get_all_active_tenants()
    token_status = []
    for t in tenants:
        token_status.append({
            "name": t["name"],
            "wsfe_ok": not is_token_expired(t["id"], "wsfe"),
            "wspci_ok": not is_token_expired(t["id"], "wspci"),
        })

    items = caea_repo.list_outbox(limit=500)
    summary = {"pending": 0, "retrying": 0, "processing": 0, "done": 0, "failed": 0}
    for item in items:
        s = item["status"]
        if s in summary:
            summary[s] += 1

    return templates.TemplateResponse("admin/monitoring.html", {
        "request": request, "active": "monitoring",
        "admin_user": "Admin",
        "token_status": token_status,
        "caea_summary": summary,
        "flash": request.session.pop("flash", None),
    })


@router.post("/admin/monitoring/retry-outbox")
async def admin_retry_outbox(request: Request):
    try:
        require_admin_session(request)
    except RequiresAdminLogin:
        return RedirectResponse(url="/portal/admin/login", status_code=303)
    init_db()
    result = await process_pending_outbox_jobs(limit=30)
    request.session["flash"] = _flash(
        "info",
        f"Outbox procesado: {result['processed']} trabajos, {result['done']} ok, {result['failed']} fallidos.",
    )
    return RedirectResponse(url="/portal/admin/monitoring", status_code=303)


# ── Tenant Login ───────────────────────────────────────────────────────────────

@router.get("/login", response_class=HTMLResponse)
def tenant_login_page(request: Request, error: str = None):
    return templates.TemplateResponse("login.html", {
        "request": request,
        "is_admin": False,
        "action_url": "/portal/login",
        "error": error,
    })


@router.post("/login")
def tenant_login_submit(request: Request, email: str = Form(...), password: str = Form(...)):
    tenant = login_tenant(request, email, password)
    if tenant:
        return RedirectResponse(url="/portal/dashboard", status_code=303)
    return templates.TemplateResponse("login.html", {
        "request": request,
        "is_admin": False,
        "action_url": "/portal/login",
        "error": "Email o contraseña incorrectos, o cuenta inactiva.",
    })


@router.get("/logout")
def tenant_logout(request: Request):
    logout_session(request)
    return RedirectResponse(url="/portal/login", status_code=303)


# ── Tenant Dashboard ───────────────────────────────────────────────────────────

@router.get("/dashboard", response_class=HTMLResponse)
def tenant_dashboard(request: Request):
    try:
        tenant = require_tenant_session(request)
    except RequiresTenantLogin:
        return RedirectResponse(url="/portal/login", status_code=303)

    certs = list_tenant_certs(tenant["id"])
    active_certs = sum(1 for c in certs if c.get("status") == "active")
    wsfe_token = get_tenant_token(tenant["id"], "wsfe")
    wspci_token = get_tenant_token(tenant["id"], "wspci")
    recent_tx = list_transactions(tenant["id"], limit=5)

    return templates.TemplateResponse("tenant/dashboard.html", {
        "request": request, "active": "dashboard",
        "tenant": tenant,
        "active_certs": active_certs,
        "calls_month": None,
        "wsfe_token": wsfe_token,
        "wspci_token": wspci_token,
        "recent_transactions": recent_tx,
        "flash": request.session.pop("flash", None),
    })


# ── Tenant API Key ─────────────────────────────────────────────────────────────

@router.get("/api-key", response_class=HTMLResponse)
def tenant_api_key(request: Request):
    try:
        tenant = require_tenant_session(request)
    except RequiresTenantLogin:
        return RedirectResponse(url="/portal/login", status_code=303)

    new_api_key = request.session.pop("new_api_key", None)
    return templates.TemplateResponse("tenant/api_key.html", {
        "request": request, "active": "api_key",
        "tenant": tenant, "new_api_key": new_api_key,
        "flash": request.session.pop("flash", None),
    })


@router.post("/api-key/rotate")
def tenant_rotate_api_key(request: Request):
    try:
        tenant = require_tenant_session(request)
    except RequiresTenantLogin:
        return RedirectResponse(url="/portal/login", status_code=303)

    _, plain_key = rotate_api_key(tenant["id"])
    request.session["new_api_key"] = plain_key
    return RedirectResponse(url="/portal/api-key", status_code=303)


# ── Tenant Certificates ────────────────────────────────────────────────────────

@router.get("/certs", response_class=HTMLResponse)
def tenant_certs(request: Request):
    try:
        tenant = require_tenant_session(request)
    except RequiresTenantLogin:
        return RedirectResponse(url="/portal/login", status_code=303)

    certs = list_tenant_certs(tenant["id"])
    for c in certs:
        c.pop("private_key_encrypted", None)
    pending_cert = next((c for c in certs if c["status"] == "pending_cert"), None)
    new_csr = request.session.pop("new_csr", None)
    return templates.TemplateResponse("tenant/certs.html", {
        "request": request, "active": "certs",
        "tenant": tenant, "certs": certs,
        "pending_cert": pending_cert, "new_csr": new_csr,
        "flash": request.session.pop("flash", None),
    })


@router.post("/certs/generate-csr")
def tenant_generate_csr(
    request: Request,
    service: str = Form(...),
    common_name: str = Form(...),
    organization: str = Form(...),
):
    try:
        tenant = require_tenant_session(request)
    except RequiresTenantLogin:
        return RedirectResponse(url="/portal/login", status_code=303)

    _, csr_pem, encrypted_key = generate_key_and_csr(
        common_name=common_name, organization=organization,
        cuit=tenant["cuit"], country="AR",
    )
    create_cert_record(
        tenant_id=tenant["id"], service=service,
        common_name=common_name, organization=organization,
        country="AR", cuit=tenant["cuit"],
        private_key_encrypted=encrypted_key, csr_pem=csr_pem,
    )
    request.session["new_csr"] = csr_pem
    request.session["flash"] = _flash("success", f"CSR generado para {service}. Envialo a AFIP.")
    return RedirectResponse(url="/portal/certs", status_code=303)


@router.post("/certs/{cert_id}/upload")
def tenant_upload_cert(request: Request, cert_id: int, cert_pem: str = Form(...)):
    try:
        tenant = require_tenant_session(request)
    except RequiresTenantLogin:
        return RedirectResponse(url="/portal/login", status_code=303)

    cert = get_cert_by_id(cert_id)
    if not cert or cert["tenant_id"] != tenant["id"]:
        request.session["flash"] = _flash("danger", "Certificado no encontrado.")
        return RedirectResponse(url="/portal/certs", status_code=303)

    valid, msg = validate_cert_pem(cert_pem)
    if not valid:
        request.session["flash"] = _flash("danger", f"Certificado inválido: {msg}")
        return RedirectResponse(url="/portal/certs", status_code=303)

    upload_cert(cert_id, cert_pem.strip())
    activate_cert(cert_id)
    request.session["flash"] = _flash("success", "Certificado cargado y activado.")
    return RedirectResponse(url="/portal/certs", status_code=303)


@router.post("/certs/{cert_id}/activate")
def tenant_activate_cert(request: Request, cert_id: int):
    try:
        tenant = require_tenant_session(request)
    except RequiresTenantLogin:
        return RedirectResponse(url="/portal/login", status_code=303)

    cert = get_cert_by_id(cert_id)
    if cert and cert["tenant_id"] == tenant["id"]:
        activate_cert(cert_id)
    return RedirectResponse(url="/portal/certs", status_code=303)


# ── Tenant Transactions ────────────────────────────────────────────────────────

@router.get("/transactions", response_class=HTMLResponse)
def tenant_transactions(request: Request):
    try:
        tenant = require_tenant_session(request)
    except RequiresTenantLogin:
        return RedirectResponse(url="/portal/login", status_code=303)

    transactions = list_transactions(tenant["id"], limit=200)
    # Refresh tenant to get latest balance
    tenant = get_tenant_by_id(tenant["id"])
    return templates.TemplateResponse("tenant/transactions.html", {
        "request": request, "active": "transactions",
        "tenant": tenant, "transactions": transactions,
        "flash": request.session.pop("flash", None),
    })


# ── Tenant Profile ─────────────────────────────────────────────────────────────

@router.get("/profile", response_class=HTMLResponse)
def tenant_profile(request: Request):
    try:
        tenant = require_tenant_session(request)
    except RequiresTenantLogin:
        return RedirectResponse(url="/portal/login", status_code=303)

    return templates.TemplateResponse("tenant/profile.html", {
        "request": request, "active": "profile",
        "tenant": tenant,
        "flash": request.session.pop("flash", None),
    })


@router.post("/profile/change-password")
def tenant_change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
):
    try:
        tenant = require_tenant_session(request)
    except RequiresTenantLogin:
        return RedirectResponse(url="/portal/login", status_code=303)

    full_tenant = get_tenant_by_id(tenant["id"])
    if not check_password(current_password, full_tenant["hashed_password"]):
        request.session["flash"] = _flash("danger", "Contraseña actual incorrecta.")
        return RedirectResponse(url="/portal/profile", status_code=303)

    if new_password != confirm_password:
        request.session["flash"] = _flash("danger", "Las contraseñas nuevas no coinciden.")
        return RedirectResponse(url="/portal/profile", status_code=303)

    if len(new_password) < 8:
        request.session["flash"] = _flash("danger", "La contraseña debe tener al menos 8 caracteres.")
        return RedirectResponse(url="/portal/profile", status_code=303)

    update_password(tenant["id"], new_password)
    request.session["flash"] = _flash("success", "Contraseña actualizada correctamente.")
    return RedirectResponse(url="/portal/profile", status_code=303)


# ── Root redirect ──────────────────────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse)
def portal_root(request: Request):
    return RedirectResponse(url="/portal/dashboard", status_code=303)
