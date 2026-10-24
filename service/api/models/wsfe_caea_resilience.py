from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class QueueSolicitCaeaRequest(BaseModel):
    Cuit: int
    Periodo: int
    Orden: int


class CaeaDetRequest(BaseModel):
    """One FECAEADetRequest item. Only CbteFch is validated here; other ARCA fields pass through."""
    model_config = ConfigDict(extra="allow")

    CbteFch: Annotated[str, Field(pattern=r"^\d{8}$")]


class CaeaFeDetReq(BaseModel):
    model_config = ConfigDict(extra="allow")

    # CantReg is forced to 1: exactly one voucher per issue-local call.
    FECAEADetRequest: Annotated[list[CaeaDetRequest], Field(min_length=1, max_length=1)]


class CaeaRegInfReq(BaseModel):
    model_config = ConfigDict(extra="allow")

    FeCabReq: dict = Field(default_factory=dict)
    FeDetReq: CaeaFeDetReq


class QueueIssueLocalInvoiceRequest(BaseModel):
    CycleId: int | None = None
    Cuit: int
    PtoVta: int
    CbteTipo: int
    # Client idempotency key (e.g. POS id + local ticket id). Same (Cuit, ClientRef) -> same invoice.
    ClientRef: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    FeCAEARegInfReq: CaeaRegInfReq


class QueuePtosVentaRequest(BaseModel):
    Cuit: int
    PtosVenta: list[int]
