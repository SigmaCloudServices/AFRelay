from fastapi import APIRouter, Depends, HTTPException, Query

from service.api.models.wsfe_caea_resilience import (
    QueueIssueLocalInvoiceRequest, QueueSolicitCaeaRequest)
from service.caea_resilience import repository as repo
from service.caea_resilience.bootstrap import resolve_current_and_next_cycles
from service.caea_resilience.db import init_db
from service.caea_resilience.outbox_worker import process_pending_outbox_jobs
from service.controllers.request_last_authorized_controller import \
    get_last_authorized_info
from service.utils.jwt_validator import verify_token
from service.utils.logger import logger

router = APIRouter()


@router.get("/wsfe/caea/queue/invoices")
async def list_caea_invoices(cuit: int, pto_vta: int | None = None, since_id: int = 0,
                             limit: int = Query(default=200, ge=1, le=500), jwt=Depends(verify_token)) -> dict:
    init_db()
    return {"status": "ok", "items": repo.list_invoices(cuit, pto_vta, since_id, limit)}


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
    if data.get("CycleId"):
        cycle = repo.get_cycle_by_id(data["CycleId"])
    else:
        cbte_fch = data["FeCAEARegInfReq"]["FeDetReq"]["FECAEADetRequest"][0]["CbteFch"]
        cycle = repo.find_cycle_for_date(data["Cuit"], cbte_fch)
    if not cycle or cycle["cuit"] != data["Cuit"]:
        raise HTTPException(status_code=404, detail="No CAEA cycle for this Cuit/date")
    if cycle.get("status") != "active" or not cycle.get("caea_code"):
        raise HTTPException(
            status_code=409,
            detail="No active CAEA code loaded for this cycle. Wait bootstrap/solicitar to complete.",
        )

    seed = None
    if not repo.has_local_invoices(data["Cuit"], data["PtoVta"], data["CbteTipo"]):
        last = await get_last_authorized_info(
            {"Cuit": data["Cuit"], "PtoVta": data["PtoVta"], "CbteTipo": data["CbteTipo"]}
        )
        if last.get("status") != "success":
            raise HTTPException(status_code=503, detail=f"Cannot read last authorized from ARCA: {last}")
        seed = int((last.get("response") or {}).get("CbteNro") or 0)

    det_req = data["FeCAEARegInfReq"]["FeDetReq"]["FECAEADetRequest"][0]
    det_req["CAEA"] = cycle["caea_code"]
    local_invoice = repo.issue_local_invoice(
        cycle_id=cycle["id"],
        cuit=data["Cuit"],
        pto_vta=data["PtoVta"],
        cbte_tipo=data["CbteTipo"],
        payload=data["FeCAEARegInfReq"],
        seed_last_nro=seed,
    )
    next_nro = local_invoice["cbte_nro"]

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
