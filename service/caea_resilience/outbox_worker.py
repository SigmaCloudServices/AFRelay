import json
import random
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from service.caea_resilience import repository as repo
from service.controllers.wsfe_caea_controller import (caea_reg_informativo,
                                                      caea_solicitar)
from service.observability.collector import emit_domain_event
from service.utils.logger import logger

AR_TZ = timezone(timedelta(hours=-3))
WINDOW_DATE_RE = re.compile(r"Del\s+(\d{2}/\d{2}/\d{4})", re.IGNORECASE)


class DeferredRetryError(RuntimeError):
    def __init__(self, message: str, next_retry_at: str):
        super().__init__(message)
        self.next_retry_at = next_retry_at


def _next_retry(attempts: int) -> str:
    base = min(3600, (2 ** attempts) * 5)
    jitter = random.randint(0, 7)
    return (datetime.now(timezone.utc) + timedelta(seconds=base + jitter)).isoformat()


async def _run_solicit(job_payload: dict[str, Any]) -> dict[str, Any]:
    cycle = job_payload["cycle"]
    response = await caea_solicitar(cycle)
    return response


async def _run_inform(job_payload: dict[str, Any]) -> dict[str, Any]:
    response = await caea_reg_informativo(job_payload["request"])
    return response


def _extract_errors(response_payload: dict[str, Any]) -> list[dict[str, Any]]:
    errors = (response_payload or {}).get("Errors")
    err_list = []
    if isinstance(errors, dict):
        candidate = errors.get("Err")
        if isinstance(candidate, list):
            err_list = [item for item in candidate if isinstance(item, dict)]
        elif isinstance(candidate, dict):
            err_list = [candidate]
    return err_list


def _deferred_retry_from_15006(response_payload: dict[str, Any]) -> str | None:
    for err in _extract_errors(response_payload):
        if str(err.get("Code")) != "15006":
            continue
        msg = str(err.get("Msg") or "")
        match = WINDOW_DATE_RE.search(msg)
        if not match:
            continue
        start_dt_local = datetime.strptime(match.group(1), "%d/%m/%Y").replace(
            hour=0, minute=5, second=0, microsecond=0, tzinfo=AR_TZ
        )
        return start_dt_local.astimezone(timezone.utc).isoformat()
    return None


async def process_pending_outbox_jobs(limit: int = 20) -> dict[str, int]:
    jobs = repo.fetch_due_outbox_jobs(limit=limit)
    done = 0
    retried = 0
    failed = 0

    for job in jobs:
        job_id = job["id"]
        payload = json.loads(job["payload_json"])
        repo.mark_outbox_processing(job_id)
        emit_domain_event(
            event_type="outbox_job",
            service="wsfe",
            status="started",
            entity_key=job["job_type"],
            payload={"job_id": job_id},
        )
        try:
            if job["job_type"] == "SOLICIT_CAEA":
                response = await _run_solicit(payload)
                if response["status"] != "success":
                    raise RuntimeError(str(response["error"]))
                response_payload = response.get("response", {}) or {}
                result_get = response_payload.get("ResultGet") or {}
                caea = result_get.get("CAEA")
                if not caea:
                    defer_until = _deferred_retry_from_15006(response_payload)
                    afip_errors = _extract_errors(response_payload)
                    error_summary = (
                        ", ".join(f"{e.get('Code')}: {e.get('Msg')}" for e in afip_errors)
                        if afip_errors
                        else "CAEA not returned by AFIP"
                    )
                    if defer_until:
                        raise DeferredRetryError(error_summary, defer_until)
                    raise RuntimeError(error_summary)
                repo.update_cycle_from_afip(payload["cycle_id"], response_payload)
            elif job["job_type"] == "INFORM_CAEA_MOVEMENT":
                response = await _run_inform(payload)
                if response["status"] != "success":
                    raise RuntimeError(str(response["error"]))
                repo.mark_invoice_informed(payload["invoice_id"])
            else:
                raise RuntimeError(f"Unknown outbox job type: {job['job_type']}")

            repo.mark_outbox_done(job_id, response)
            done += 1
            emit_domain_event(
                event_type="outbox_job",
                service="wsfe",
                status="success",
                entity_key=job["job_type"],
                payload={"job_id": job_id},
            )

        except Exception as exc:
            attempts = int(job["attempts"]) + 1
            next_retry = _next_retry(attempts)
            if isinstance(exc, DeferredRetryError):
                next_retry = exc.next_retry_at
            repo.mark_outbox_retry(job_id, attempts, next_retry, str(exc))
            logger.warning("Outbox job %s failed (attempt %s): %s", job_id, attempts, exc)
            if job["job_type"] == "SOLICIT_CAEA":
                if isinstance(exc, DeferredRetryError):
                    repo.set_cycle_status(payload["cycle_id"], "requested", str(exc))
                else:
                    repo.set_cycle_error(payload["cycle_id"], str(exc))
            elif job["job_type"] == "INFORM_CAEA_MOVEMENT":
                repo.mark_invoice_error(payload["invoice_id"], str(exc))
            if attempts >= 10:
                failed += 1
            else:
                retried += 1
            emit_domain_event(
                event_type="outbox_job",
                service="wsfe",
                status="error",
                entity_key=job["job_type"],
                error_type=type(exc).__name__,
                payload={"job_id": job_id, "attempts": attempts},
            )

    return {"processed": len(jobs), "done": done, "retried": retried, "failed": failed}
