from typing import Any

from pydantic import BaseModel


class WsfeAuthRequest(BaseModel):
    Cuit: int


class WsfeCaeaPeriodoOrdenRequest(WsfeAuthRequest):
    Periodo: int
    Orden: int


class WsfeCaeaSinMovimientoRequest(WsfeAuthRequest):
    PtoVta: int
    CAEA: str


class WsfeCaeaSinMovimientoConsultarRequest(WsfeAuthRequest):
    PtoVta: int
    CAEA: str | None = None


class WsfeCaeaRegInformativoRequest(WsfeAuthRequest):
    FeCAEARegInfReq: dict[str, Any]
