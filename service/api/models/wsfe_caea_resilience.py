from pydantic import BaseModel


class QueueSolicitCaeaRequest(BaseModel):
    Cuit: int
    Periodo: int
    Orden: int


class QueueIssueLocalInvoiceRequest(BaseModel):
    CycleId: int
    Cuit: int
    PtoVta: int
    CbteTipo: int
    FeCAEARegInfReq: dict

