import os
from datetime import datetime, timedelta, timezone

from service.caea_resilience import repository as repo
from service.caea_resilience.db import init_db
from service.caea_resilience.outbox_worker import process_pending_outbox_jobs
from service.utils.logger import logger

AR_TZ = timezone(timedelta(hours=-3))


def _month_roll(year: int, month: int) -> tuple[int, int]:
    if month == 12:
        return year + 1, 1
    return year, month + 1


def resolve_current_and_next_cycles(now: datetime | None = None) -> list[tuple[int, int]]:
    actual = (now or datetime.now(timezone.utc)).astimezone(AR_TZ)
    year = actual.year
    month = actual.month
    periodo = year * 100 + month

    if actual.day <= 15:
        return [(periodo, 1), (periodo, 2)]

    next_year, next_month = _month_roll(year, month)
    next_periodo = next_year * 100 + next_month
    return [(periodo, 2), (next_periodo, 1)]


def bootstrap_cuit_cycles(cuit: int) -> dict[str, int]:
    ensured = 0
    queued = 0
    for periodo, orden in resolve_current_and_next_cycles():
        cycle = repo.create_cycle(cuit, periodo, orden)
        ensured += 1
        if cycle.get("status") == "active" and cycle.get("caea_code"):
            continue
        job = repo.add_outbox_job(
            job_type="SOLICIT_CAEA",
            idempotency_key=f"solicit:{cuit}:{periodo}:{orden}",
            payload={"cycle_id": cycle["id"], "cycle": {"Cuit": cuit, "Periodo": periodo, "Orden": orden}},
        )
        if job["status"] in ("pending", "retrying", "processing"):
            queued += 1
    return {"ensured": ensured, "queued": queued}


def _configured_cuits() -> list[int]:
    raw = os.getenv("CAEA_BOOTSTRAP_CUITS", "").strip()
    if not raw:
        return []
    values = []
    for chunk in raw.split(","):
        piece = chunk.strip()
        if not piece:
            continue
        try:
            values.append(int(piece))
        except ValueError:
            logger.warning("Ignoring invalid CUIT in CAEA_BOOTSTRAP_CUITS: %s", piece)
    return values


async def bootstrap_caea_cycles_once() -> dict:
    init_db()
    repo.normalize_cycle_statuses()
    cuits = _configured_cuits()
    if not cuits:
        logger.info("CAEA bootstrap skipped: no CAEA_BOOTSTRAP_CUITS configured")
        return {"status": "skipped", "reason": "no_cuits", "processed_cuits": 0}

    summary = {"processed_cuits": 0, "ensured_cycles": 0, "queued_jobs": 0}
    for cuit in cuits:
        result = bootstrap_cuit_cycles(cuit)
        summary["processed_cuits"] += 1
        summary["ensured_cycles"] += result["ensured"]
        summary["queued_jobs"] += result["queued"]

    outbox = await process_pending_outbox_jobs(limit=100)
    logger.info(
        "CAEA bootstrap done: cuits=%s ensured=%s queued=%s outbox=%s",
        summary["processed_cuits"],
        summary["ensured_cycles"],
        summary["queued_jobs"],
        outbox,
    )
    return {"status": "ok", "summary": summary, "outbox": outbox}
