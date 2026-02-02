import pytest
from httpx import AsyncClient


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
                        "ImpNeto": 100.0,
                        "ImpTotConc": 0.0,
                        "ImpOpEx": 0.0,
                        "ImpTrib": 0.0,
                        "ImpIVA": 0.0,
                        "MonId": "PES",
                        "MonCotiz": 1,
                        "CondicionIVAReceptorId": 5,
                    }
                ]
            },
        },
    }


def _collect_error_messages(resp_json: dict) -> list[str]:
    details = resp_json.get("detail", [])
    return [item.get("msg", "") for item in details if isinstance(item, dict)]


@pytest.mark.asyncio
async def test_generate_invoice_rejects_invalid_date_format(client: AsyncClient, override_auth):
    payload = _base_payload()
    payload["FeCAEReq"]["FeDetReq"]["FECAEDetRequest"][0]["CbteFch"] = "2026-01-25"

    resp = await client.post("/wsfe/invoices", json=payload)

    assert resp.status_code == 422
    messages = _collect_error_messages(resp.json())
    assert any("yyyymmdd" in msg for msg in messages)


@pytest.mark.asyncio
async def test_generate_invoice_rejects_missing_service_dates_for_concept_2(client: AsyncClient, override_auth):
    payload = _base_payload()
    payload["FeCAEReq"]["FeDetReq"]["FECAEDetRequest"][0]["Concepto"] = 2

    resp = await client.post("/wsfe/invoices", json=payload)

    assert resp.status_code == 422
    messages = _collect_error_messages(resp.json())
    assert any("Concepto 2 or 3 requires" in msg for msg in messages)


@pytest.mark.asyncio
async def test_generate_invoice_rejects_inconsistent_totals(client: AsyncClient, override_auth):
    payload = _base_payload()
    payload["FeCAEReq"]["FeDetReq"]["FECAEDetRequest"][0]["ImpTotal"] = 50.0

    resp = await client.post("/wsfe/invoices", json=payload)

    assert resp.status_code == 422
    messages = _collect_error_messages(resp.json())
    assert any("ImpTotal must equal" in msg for msg in messages)
