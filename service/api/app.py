import os
import secrets
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, status
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from fastapi.middleware import Middleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException
from starlette.middleware.sessions import SessionMiddleware

from service.api import (admin, ui_frontend, ui_monitoring, ui_portal,
                         wsaa, wsfe, wsfe_caea_resilience, wspci)
from service.api.middleware.observability import ObservabilityMiddleware
from service.caea_resilience.bootstrap import bootstrap_caea_cycles_once
from service.caea_resilience.db import init_db as init_caea_db
from service.controllers.readiness_health_controller import readiness_health_check
from service.tenants.db import init_db as init_tenant_db
from service.utils.afip_token_scheduler import start_scheduler, stop_scheduler
from service.utils.logger import logger

load_dotenv(override=False)

SECRET_KEY = os.getenv("SECRET_KEY", "change-me-insecure-secret-key-32bytes!")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_caea_db()
    init_tenant_db()
    await bootstrap_caea_cycles_once()
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(
    lifespan=lifespan,
    middleware=[Middleware(ObservabilityMiddleware)],
)

# Session middleware — must be added before routes are registered
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, session_cookie="afrelay_session")

# Static files for portal
_STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ui", "static")
app.mount("/portal/static", StaticFiles(directory=_STATIC_DIR), name="portal_static")

# API Routers
app.include_router(wsaa.router)
app.include_router(wsfe.router)
app.include_router(wsfe_caea_resilience.router)
app.include_router(wspci.router)
app.include_router(ui_monitoring.router)
app.include_router(ui_frontend.router)

# Admin & Portal Routers
app.include_router(admin.router)
app.include_router(ui_portal.router)


# ===================
# == HEALTH CHECKS ==
# ===================

@app.get("/health/liveness")
def liveness() -> dict:
    return {"health": "OK"}


@app.get("/health/readiness")
async def readiness() -> dict:
    result = await readiness_health_check()
    return result


# ===================
# === DOCS CONFIG ===
# ===================

security = HTTPBasic()

DOCS_USERNAME = os.getenv("DOCS_USERNAME", "docs")
DOCS_PASSWORD = os.getenv("DOCS_PASSWORD", "docs")


def verify_credentials(credentials: HTTPBasicCredentials = Depends(security)):
    correct_username = secrets.compare_digest(credentials.username, DOCS_USERNAME)
    correct_password = secrets.compare_digest(credentials.password, DOCS_PASSWORD)
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Basic"},
        )
    return True


@app.get("/docs", include_in_schema=False)
def custom_swagger_ui(credentials: bool = Depends(verify_credentials)):
    return get_swagger_ui_html(openapi_url="/openapi.json", title="AFRelay API")


@app.get("/openapi.json", include_in_schema=False)
def openapi(credentials: bool = Depends(verify_credentials)):
    return JSONResponse(
        get_openapi(title="AFRelay API", version="2.0.0", routes=app.routes)
    )
