from typing import Literal

from fastapi import APIRouter, Depends, Query

from service.caea_resilience import repository as caea_repo
from service.caea_resilience.db import init_db
from service.caea_resilience.outbox_worker import process_pending_outbox_jobs
from service.observability.collector import (get_store,
                                             refresh_token_state_from_files)
from service.utils.jwt_validator import verify_token

router = APIRouter()


@router.get("/ui/metrics/summary")
async def ui_metrics_summary(
    window_minutes: int = Query(default=60, ge=1, le=1440),
    jwt=Depends(verify_token),
) -> dict:
    store = get_store()
    return store.get_summary(window_minutes=window_minutes)


@router.get("/ui/logs")
async def ui_logs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
    endpoint: str | None = None,
    status: Literal["ok", "error"] | None = None,
    service: str | None = None,
    error_type: str | None = None,
    jwt=Depends(verify_token),
) -> dict:
    store = get_store()
    return store.list_logs(
        page=page,
        page_size=page_size,
        endpoint=endpoint,
        status=status,
        service=service,
        error_type=error_type,
    )


@router.get("/ui/errors")
async def ui_errors(
    window_minutes: int = Query(default=60, ge=1, le=1440),
    group_by: Literal["error_type", "endpoint"] = "error_type",
    jwt=Depends(verify_token),
) -> dict:
    store = get_store()
    return store.get_errors(window_minutes=window_minutes, group_by=group_by)


@router.get("/ui/tokens/status")
async def ui_tokens_status(jwt=Depends(verify_token)) -> dict:
    refresh_token_state_from_files()
    store = get_store()
    return store.get_token_status()


@router.get("/ui/operations/summary")
async def ui_operations_summary(
    window_minutes: int = Query(default=60, ge=1, le=1440),
    jwt=Depends(verify_token),
) -> dict:
    store = get_store()
    return store.get_operations_summary(window_minutes=window_minutes)


@router.get("/ui/alerts")
async def ui_alerts(jwt=Depends(verify_token)) -> dict:
    refresh_token_state_from_files()
    store = get_store()
    return store.get_alerts()


@router.get("/ui/events")
async def ui_events(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
    service: str | None = None,
    event_type: str | None = None,
    status: Literal["success", "error"] | None = None,
    jwt=Depends(verify_token),
) -> dict:
    store = get_store()
    return store.list_domain_events(
        page=page,
        page_size=page_size,
        service=service,
        event_type=event_type,
        status=status,
    )


@router.get("/ui/caea/queue")
async def ui_caea_queue(
    limit: int = Query(default=200, ge=1, le=1000),
    jwt=Depends(verify_token),
) -> dict:
    init_db()
    items = caea_repo.list_outbox(limit=limit)
    summary = {
        "pending": 0,
        "retrying": 0,
        "processing": 0,
        "done": 0,
        "failed": 0,
    }
    for item in items:
        status = item["status"]
        if status in summary:
            summary[status] += 1
    return {"summary": summary, "items": items}


@router.post("/ui/caea/queue/retry")
async def ui_caea_queue_retry(
    limit: int = Query(default=30, ge=1, le=200),
    jwt=Depends(verify_token),
) -> dict:
    init_db()
    result = await process_pending_outbox_jobs(limit=limit)
    return {"status": "ok", "result": result}


@router.get("/ui/caea/assignments")
async def ui_caea_assignments(
    limit: int = Query(default=200, ge=1, le=1000),
    jwt=Depends(verify_token),
) -> dict:
    init_db()
    items = caea_repo.list_caea_assignments(limit=limit)
    return {"items": items, "count": len(items)}
