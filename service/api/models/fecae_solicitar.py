import math
import re

from pydantic import BaseModel, ConfigDict, Field, model_validator

DATE_YYYYMMDD_RE = re.compile(r"^\d{8}$")


def _is_valid_yyyymmdd(value: str) -> bool:
    return bool(DATE_YYYYMMDD_RE.fullmatch(value))


class Actividad(BaseModel):
    Id: int

class Actividades(BaseModel):
    Actividad: list[Actividad]

class PeriodoAsoc(BaseModel):
    FchDesde: str
    FchHasta: str

class Comprador(BaseModel):
    DocTipo: int
    DocNro: int
    Porcentaje: float

class Compradores(BaseModel):
    Comprador: list[Comprador]

class Opcional(BaseModel):
    Id: str
    Valor: str

class Opcionales(BaseModel):
    Opcional: list[Opcional]

class AlicIva(BaseModel):
    Id: int
    BaseImp: float
    Importe: float

class Iva(BaseModel):
    AlicIva: list[AlicIva]

class Tributo(BaseModel):
    Id: int
    Desc: str | None = None
    BaseImp: float
    Alic: float
    Importe: float

class Tributos(BaseModel):
    Tributo: list[Tributo]

class CbteAsoc(BaseModel):
    Tipo: int
    PtoVta: int
    Nro: int
    Cuit: str | None = None
    CbteFch: str

class CbtesAsoc(BaseModel):
    CbteAsoc : list[CbteAsoc]

class FECAEDetRequest(BaseModel):

    model_config = ConfigDict(populate_by_name=True)

    Concepto: int
    DocTipo: int
    DocNro: int
    CbteDesde: int
    CbteHasta: int
    CbteFch: str
    ImpTotal: float
    ImpTotConc: float
    ImpNeto: float
    ImpOpEx: float
    ImpTrib: float
    ImpIVA: float
    FchServDesde: str | None = None
    FchServHasta: str | None = None
    FchVtoPago: str | None = None
    MonId: str
    MonCotiz: float | None = 0.0
    CanMisMonExt: str | None = None
    CondicionIVAReceptorId: int

    cbtes_asoc: CbtesAsoc | None = Field(None, alias="CbtesAsoc")
    tributos: Tributos | None = Field(None, alias="Tributos")
    iva: Iva | None = Field(None, alias="Iva")
    opcionales: Opcionales | None = Field(None, alias="Opcionales")
    compradores: Compradores | None = Field(None, alias="Compradores")
    periodo_asoc: PeriodoAsoc | None = Field(None, alias="PeriodoAsoc")
    actividades: Actividades | None = Field(None, alias="Actividades")

    @model_validator(mode="after")
    def validate_business_rules(self):
        dates_to_check = [("CbteFch", self.CbteFch)]
        if self.FchServDesde is not None:
            dates_to_check.append(("FchServDesde", self.FchServDesde))
        if self.FchServHasta is not None:
            dates_to_check.append(("FchServHasta", self.FchServHasta))
        if self.FchVtoPago is not None:
            dates_to_check.append(("FchVtoPago", self.FchVtoPago))

        for label, value in dates_to_check:
            if not _is_valid_yyyymmdd(value):
                raise ValueError(f"{label} must use yyyymmdd format")

        if self.CbteDesde > self.CbteHasta:
            raise ValueError("CbteDesde must be less than or equal to CbteHasta")

        if self.Concepto in (2, 3):
            missing = [
                label
                for label, value in (
                    ("FchServDesde", self.FchServDesde),
                    ("FchServHasta", self.FchServHasta),
                    ("FchVtoPago", self.FchVtoPago),
                )
                if value is None
            ]
            if missing:
                raise ValueError(
                    "Concepto 2 or 3 requires FchServDesde, FchServHasta and FchVtoPago"
                )

        expected_total = (
            self.ImpTotConc + self.ImpNeto + self.ImpOpEx + self.ImpTrib + self.ImpIVA
        )
        if not math.isclose(self.ImpTotal, expected_total, rel_tol=0.0, abs_tol=0.01):
            raise ValueError(
                "ImpTotal must equal ImpTotConc + ImpNeto + ImpOpEx + ImpTrib + ImpIVA"
            )

        if self.MonId == "PES" and not math.isclose(self.MonCotiz or 0.0, 1.0, rel_tol=0.0, abs_tol=0.0001):
            raise ValueError("MonCotiz must be 1 for MonId PES")

        if self.MonId != "PES":
            if self.MonCotiz is None or self.MonCotiz <= 0:
                raise ValueError("MonCotiz must be greater than 0 when MonId is not PES")

        return self

class FeDetReq(BaseModel):
    FECAEDetRequest: list[FECAEDetRequest]

class FeCabReq(BaseModel):
    CantReg: int
    PtoVta: int
    CbteTipo: int

class FeCAEReq(BaseModel):
    FeCabReq: FeCabReq
    FeDetReq: FeDetReq

    @model_validator(mode="after")
    def validate_cant_reg(self):
        detail_rows = len(self.FeDetReq.FECAEDetRequest)
        if self.FeCabReq.CantReg != detail_rows:
            raise ValueError("FeCabReq.CantReg must match FECAEDetRequest size")
        return self

class Auth(BaseModel):
    """
    Token and Sign will taken 
    from loginTicketResponse in the service
    """
    Cuit: int

class RootModel(BaseModel):
    Auth: Auth
    FeCAEReq: FeCAEReq
