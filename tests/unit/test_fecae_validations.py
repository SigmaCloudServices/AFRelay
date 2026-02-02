import pytest
from pydantic import ValidationError

from service.api.models.fecae_solicitar import RootModel


def _base_payload():
    return {
        "Auth": {"Cuit": 30740253022},
        "FeCAEReq": {
            "FeCabReq": {"CantReg": 1, "PtoVta": 1, "CbteTipo": 11},
            "FeDetReq": {
                "FECAEDetRequest": [
                    {
                        "Concepto": 1,
                        "DocTipo": 99,
                        "DocNro": 0,
                        "CbteDesde": 2,
                        "CbteHasta": 2,
                        "CbteFch": "20260125",
                        "ImpTotal": 100.0,
                        "ImpTotConc": 0.0,
                        "ImpNeto": 100.0,
                        "ImpOpEx": 0.0,
                        "ImpTrib": 0.0,
                        "ImpIVA": 0.0,
                        "MonId": "PES",
                        "MonCotiz": 1.0,
                        "CondicionIVAReceptorId": 5,
                    }
                ]
            },
        },
    }


def test_fecae_payload_valid_base_case():
    payload = _base_payload()
    model = RootModel.model_validate(payload)
    assert model.FeCAEReq.FeCabReq.CantReg == 1


def test_fecae_rejects_invalid_date_format():
    payload = _base_payload()
    payload["FeCAEReq"]["FeDetReq"]["FECAEDetRequest"][0]["CbteFch"] = "2026-01-25"

    with pytest.raises(ValidationError, match="yyyymmdd"):
        RootModel.model_validate(payload)


def test_fecae_requires_service_dates_for_concept_2_and_3():
    payload = _base_payload()
    payload["FeCAEReq"]["FeDetReq"]["FECAEDetRequest"][0]["Concepto"] = 2

    with pytest.raises(ValidationError, match="Concepto 2 or 3 requires"):
        RootModel.model_validate(payload)


def test_fecae_validates_totals_consistency():
    payload = _base_payload()
    payload["FeCAEReq"]["FeDetReq"]["FECAEDetRequest"][0]["ImpTotal"] = 99.0

    with pytest.raises(ValidationError, match="ImpTotal must equal"):
        RootModel.model_validate(payload)


def test_fecae_validates_currency_rules():
    payload = _base_payload()
    payload["FeCAEReq"]["FeDetReq"]["FECAEDetRequest"][0]["MonCotiz"] = 0.5

    with pytest.raises(ValidationError, match="MonCotiz must be 1 for MonId PES"):
        RootModel.model_validate(payload)

    payload = _base_payload()
    row = payload["FeCAEReq"]["FeDetReq"]["FECAEDetRequest"][0]
    row["MonId"] = "USD"
    row["MonCotiz"] = 0

    with pytest.raises(ValidationError, match="MonCotiz must be greater than 0"):
        RootModel.model_validate(payload)


def test_fecae_validates_cant_reg_matches_rows():
    payload = _base_payload()
    payload["FeCAEReq"]["FeCabReq"]["CantReg"] = 2

    with pytest.raises(ValidationError, match="CantReg must match"):
        RootModel.model_validate(payload)


def test_fecae_valid_service_case_for_concept_2():
    payload = _base_payload()
    row = payload["FeCAEReq"]["FeDetReq"]["FECAEDetRequest"][0]
    row["Concepto"] = 2
    row["FchServDesde"] = "20260101"
    row["FchServHasta"] = "20260131"
    row["FchVtoPago"] = "20260210"

    model = RootModel.model_validate(payload)
    assert model.FeCAEReq.FeDetReq.FECAEDetRequest[0].Concepto == 2
