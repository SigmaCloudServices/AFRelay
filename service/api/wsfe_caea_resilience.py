from fastapi import APIRouter, Depends, HTTPException, Query

from service.api.models.wsfe_caea_resilience import (
    QueueIssueLocalInvoiceRequest, QueueSolicitCaeaRequest)
from service.caea_resilience import repository as repo
from service.caea_resilience.bootstrap import resolve_current_and_next_cycles
from service.caea_resilience.db import init_db
from service.caea_resilience.outbox_worker import process_pending_outbox_jobs
from service.utils.jwt_validator import verify_token
from service.utils.logger import logger

router = APIRouter()


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


@router.post("/wsfe/caea/queue/issue-local")
async def queue_issue_local_invoice(payload: QueueIssueLocalInvoiceRequest, jwt=Depends(verify_token)) -> dict:
    init_db()
    data = payload.model_dump()
    cycle = repo.get_cycle_by_id(data["CycleId"])
    if not cycle or cycle["cuit"] != data["Cuit"]:
        raise HTTPException(status_code=404, detail="CAEA cycle not found for given CycleId/Cuit")
    if cycle.get("status") != "active" or not cycle.get("caea_code"):
        raise HTTPException(
            status_code=409,
            detail="No active CAEA code loaded for this cycle. Wait bootstrap/solicitar to complete.",
        )

    next_nro = repo.reserve_next_invoice_number(data["Cuit"], data["PtoVta"], data["CbteTipo"])

    det_req = data["FeCAEARegInfReq"]["FeDetReq"]["FECAEADetRequest"][0]
    det_req["CbteDesde"] = next_nro
    det_req["CbteHasta"] = next_nro
    det_req["CAEA"] = cycle["caea_code"]

    local_invoice = repo.create_local_invoice(
        cycle_id=data["CycleId"],
        cuit=data["Cuit"],
        pto_vta=data["PtoVta"],
        cbte_tipo=data["CbteTipo"],
        cbte_nro=next_nro,
        payload=data["FeCAEARegInfReq"],
    )

    request = {"Cuit": data["Cuit"], "FeCAEARegInfReq": data["FeCAEARegInfReq"]}
    job = repo.add_outbox_job(
        job_type="INFORM_CAEA_MOVEMENT",
        idempotency_key=f"inform:{data['Cuit']}:{data['PtoVta']}:{data['CbteTipo']}:{next_nro}",
        payload={"invoice_id": local_invoice["id"], "request": request},
    )
    return {
        "status": "queued",
        "reserved_cbte_nro": next_nro,
        "caea": cycle["caea_code"],
        "invoice": local_invoice,
        "job": job,
    }


@router.post("/wsfe/caea/queue/retry")
async def retry_outbox(limit: int = Query(default=20, ge=1, le=200), jwt=Depends(verify_token)) -> dict:
    init_db()
    result = await process_pending_outbox_jobs(limit=limit)
    return {"status": "ok", "result": result}


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
                "periodo": periodo,
                "orden": orden,
                "active": bool(active),
                "caea_code": (active or {}).get("caea_code"),
                "status": (cycle or {}).get("status"),
            }
        )
    return {"status": "ok", "cycles": cycles}
