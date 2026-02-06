from pydantic import BaseModel


class WsfeAuthRequest(BaseModel):
    Cuit: int


class WsfeCondicionIvaReceptorRequest(WsfeAuthRequest):
    ClaseCmp: str | None = None


class WsfeCotizacionRequest(WsfeAuthRequest):
    MonId: str
    FchCotiz: str | None = None
