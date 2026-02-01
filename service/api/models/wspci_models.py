from pydantic import BaseModel


class GetPersonaRequest(BaseModel):
    cuitRepresentada: int
    idPersona: int
