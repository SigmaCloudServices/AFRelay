from pydantic import BaseModel


class WsfeAuthRequest(BaseModel):
    Cuit: int


class WsfeCondicionIvaReceptorRequest(WsfeAuthRequest):
    ClaseCmp: str | None = None
