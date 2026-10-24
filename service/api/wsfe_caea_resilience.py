from fastapi import APIRouter, Depends, HTTPException, Query

from service.api.models.wsfe_caea_resilience import (
    QueueIssueLocalInvoiceRequest, QueuePtosVentaRequest,
    QueueSolicitCaeaRequest)
from service.caea_resilience import repository as repo
from service.caea_resilience.bootstrap import (bootstrap_cuit_cycles,
                                              resolve_current_and_next_cycles)
from service.caea_resilience.db import init_db
from service.caea_resilience.numbering import (LastAuthorizedUnavailable,
                                               read_last_authorized,
                                               seed_numbering)
from service.caea_resilience.outbox_worker import process_pending_outbox_jobs
from service.utils.jwt_validator import verify_token
from service.utils.logger import logger

router = APIRouter()


@router.get("/wsfe/caea/queue/invoices")
async def list_caea_invoices(cuit: int, pto_vta: int | None = None, since_id: int = 0,
                             updated_since: str | None = None, cbte_tipo: int | None = None,
                             cbte_nro: int | None = None,
                             limit: int = Query(default=200, ge=1, le=500), jwt=Depends(verify_token)) -> dict:
    """since_id alone: new invoices by id. updated_since (+ since_id as tie-break): every status change."""
    init_db()
    normalized = None
    if updated_since is not None:
        try:
            normalized = repo.normalize_timestamp(updated_since)
        except ValueError:
            raise HTTPException(status_code=422, detail="updated_since must be an ISO 8601 timestamp")
    items = repo.list_invoices(cuit, pto_vta, since_id, limit, updated_since=normalized,
                               cbte_tipo=cbte_tipo, cbte_nro=cbte_nro)
    return {"status": "ok", "items": items}


@router.post("/wsfe/caea/queue/solicitar")
async def queue_solicitar_caea(payload: QueueSolicitCaeaRequest, jwt=Depends(verify_token)) -> dict:
    init_db()
    data = payload.model_dump()
    cycle = repo.create_cycle(data["Cuit"], data["Periodo"], data["Orden"])
    job = repo.add_outbox_job(
        job_type="SOLICIT_CAEA",
        idempotency_key=f"solicit:{data['Cuit']}:{data['Periodo']}:{data['Orden']}",
        payload={"cycle_id": cycle["id"], "cycle": data},
    )
    logger.info("Queued CAEA solicit request for cycle id=%s", cycle["id"])
    return {"status": "queued", "cycle": cycle, "job": job}


def _issue_response(invoice: dict) -> dict:
    """Same shape for a new invoice and for a ClientRef replay."""
    cycle = repo.get_cycle_by_id(invoice["cycle_id"]) or {}
    job = repo.get_outbox_job_by_key(
        repo.inform_idempotency_key(invoice["cuit"], invoice["pto_vta"], invoice["cbte_tipo"], invoice["cbte_nro"]))
    if job is not None:
        job.pop("payload_json", None)
    return {
        "status": "queued",
        "reserved_cbte_nro": invoice["cbte_nro"],
        "caea": cycle.get("caea_code"),
        "fch_vig_hasta": cycle.get("fch_vig_hasta"),
        "fch_tope_inf": cycle.get("fch_tope_inf"),
        "invoice": repo.public_invoice(invoice),
        "job": job,
    }


def _replay(invoice: dict, data: dict) -> dict:
    if (invoice["pto_vta"], invoice["cbte_tipo"]) != (data["PtoVta"], data["CbteTipo"]):
        raise HTTPException(status_code=409, detail="ClientRef already used for another PtoVta/CbteTipo")
    return _issue_response(invoice)


@router.post("/wsfe/caea/queue/issue-local")
async def queue_issue_local_invoice(payload: QueueIssueLocalInvoiceRequest, jwt=Depends(verify_token)) -> dict:
    init_db()
    data = payload.model_dump()
    cuit, pto_vta, cbte_tipo, client_ref = data["Cuit"], data["PtoVta"], data["CbteTipo"], data.get("ClientRef")
    if client_ref is not None:
        existing = repo.get_invoice_by_client_ref(cuit, client_ref)
        if existing is not None:
            return _replay(existing, data)

    if data.get("CycleId"):
        cycle = repo.get_cycle_by_id(data["CycleId"])
    else:
        cbte_fch = data["FeCAEARegInfReq"]["FeDetReq"]["FECAEADetRequest"][0]["CbteFch"]
        cycle = repo.find_cycle_for_date(cuit, cbte_fch)
    if not cycle or cycle["cuit"] != cuit:
        raise HTTPException(status_code=404, detail="No CAEA cycle for this Cuit/date")
    if cycle.get("status") != "active" or not cycle.get("caea_code"):
        raise HTTPException(
            status_code=409,
            detail="No active CAEA code loaded for this cycle. Wait bootstrap/solicitar to complete.",
        )

    # Numbering: MAX(local) -> seeded caea_numbering -> (last resort) ARCA live.
    seed = None
    if not repo.has_local_invoices(cuit, pto_vta, cbte_tipo) and repo.get_numbering(cuit, pto_vta, cbte_tipo) is None:
        try:
            seed = await read_last_authorized(cuit, pto_vta, cbte_tipo)
        except LastAuthorizedUnavailable as exc:
            raise HTTPException(status_code=503, detail=f"Sin numeracion inicial para PV {pto_vta} tipo {cbte_tipo}: {exc}")

    local_invoice = repo.issue_local_invoice(
        cycle_id=cycle["id"],
        cuit=cuit,
        pto_vta=pto_vta,
        cbte_tipo=cbte_tipo,
        payload=data["FeCAEARegInfReq"],
        seed_last_nro=seed,
        client_ref=client_ref,
    )
    if client_ref is not None:
        # The row may come from a concurrent call with the same ClientRef that won the race.
        return _replay(local_invoice, data)
    return _issue_response(local_invoice)


@router.post("/wsfe/caea/queue/retry")
async def retry_outbox(limit: int = Query(default=20, ge=1, le=200), jwt=Depends(verify_token)) -> dict:
    init_db()
    revived = repo.revive_failed_outbox_jobs()
    result = await process_pending_outbox_jobs(limit=limit)
    return {"status": "ok", "revived": revived, "result": result}


@router.get("/wsfe/caea/queue/outbox")
async def list_outbox(status: str | None = None, limit: int = Query(default=100, ge=1, le=500), jwt=Depends(verify_token)) -> dict:
    init_db()
    items = repo.list_outbox(status=status, limit=limit)
    return {"status": "ok", "items": items}


@router.get("/wsfe/caea/queue/active")
async def active_caea(cuit: int, jwt=Depends(verify_token)) -> dict:
    init_db()
    cycles = []
    for periodo, orden in resolve_current_and_next_cycles():
        active = repo.get_active_cycle(cuit, periodo, orden)
        cycle = repo.get_cycle(cuit, periodo, orden)
        cycles.append(
            {
                "cycle_id": (cycle or {}).get("id"),
                "periodo": periodo,
                "orden": orden,
                "fch_vig_desde": (cycle or {}).get("fch_vig_desde"),
                "fch_vig_hasta": (cycle or {}).get("fch_vig_hasta"),
                "fch_tope_inf": (cycle or {}).get("fch_tope_inf"),
                "active": bool(active),
                "caea_code": (active or {}).get("caea_code"),
                "status": (cycle or {}).get("status"),
            }
        )
    return {"status": "ok", "cycles": cycles}


@router.put("/wsfe/caea/queue/ptos-venta")
async def set_caea_ptos_venta(payload: QueuePtosVentaRequest, jwt=Depends(verify_token)) -> dict:
    init_db()
    repo.set_ptos_venta(payload.Cuit, payload.PtosVenta)
    bootstrap_cuit_cycles(payload.Cuit)
    # Seed initial numbering while ARCA is reachable; failures are reported, never raised.
    try:
        seeding = await seed_numbering(payload.Cuit)
    except Exception as exc:  # seed_numbering does not raise; belt and braces for the PUT contract
        logger.warning("CAEA numbering seed raised for cuit=%s: %r", payload.Cuit, exc)
        seeding = {"seeded": 0, "skipped": 0, "errors": [{"pto_vta": None, "cbte_tipo": None, "error": type(exc).__name__}]}
    return {"status": "ok", "cuit": payload.Cuit, "ptos_venta": payload.PtosVenta, "seeding": seeding}


@router.get("/wsfe/caea/queue/cycles")
async def list_caea_cycles(cuit: int, jwt=Depends(verify_token)) -> dict:
    init_db()
    return {"status": "ok", "items": repo.list_cycles_with_pvs(cuit)}
