import pytest
from httpx import AsyncClient


REQUESTS_AND_RESPONSES = [
    (
        "/wsfe/caea/solicitar",
        {
            "Cuit": 30740253022,
            "Periodo": 202601,
            "Orden": 1,
        },
        """<?xml version="1.0" encoding="utf-8"?>
<soap-env:Envelope xmlns:soap-env="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ar="http://ar.gov.afip.dif.FEV1/">
  <soap-env:Body>
    <ar:FECAEASolicitarResponse>
      <ar:FECAEASolicitarResult>
        <ar:ResultGet>
          <ar:CAEA>61234567890123</ar:CAEA>
          <ar:Periodo>202601</ar:Periodo>
          <ar:Orden>1</ar:Orden>
        </ar:ResultGet>
      </ar:FECAEASolicitarResult>
    </ar:FECAEASolicitarResponse>
  </soap-env:Body>
</soap-env:Envelope>
""",
    ),
    (
        "/wsfe/caea/consultar",
        {
            "Cuit": 30740253022,
            "Periodo": 202601,
            "Orden": 1,
        },
        """<?xml version="1.0" encoding="utf-8"?>
<soap-env:Envelope xmlns:soap-env="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ar="http://ar.gov.afip.dif.FEV1/">
  <soap-env:Body>
    <ar:FECAEAConsultarResponse>
      <ar:FECAEAConsultarResult>
        <ar:ResultGet>
          <ar:CAEA>61234567890123</ar:CAEA>
          <ar:Periodo>202601</ar:Periodo>
          <ar:Orden>1</ar:Orden>
        </ar:ResultGet>
      </ar:FECAEAConsultarResult>
    </ar:FECAEAConsultarResponse>
  </soap-env:Body>
</soap-env:Envelope>
""",
    ),
    (
        "/wsfe/caea/informar",
        {
            "Cuit": 30740253022,
            "FeCAEARegInfReq": {
                "FeCabReq": {
                    "CantReg": 1,
                    "PtoVta": 1,
                    "CbteTipo": 11,
                },
                "FeDetReq": {
                    "FECAEADetRequest": [
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
                            "CAEA": "61234567890123",
                        }
                    ]
                },
            },
        },
        """<?xml version="1.0" encoding="utf-8"?>
<soap-env:Envelope xmlns:soap-env="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ar="http://ar.gov.afip.dif.FEV1/">
  <soap-env:Body>
    <ar:FECAEARegInformativoResponse>
      <ar:FECAEARegInformativoResult>
        <ar:FeCabResp>
          <ar:Cuit>30740253022</ar:Cuit>
          <ar:PtoVta>1</ar:PtoVta>
          <ar:CbteTipo>11</ar:CbteTipo>
          <ar:FchProceso>20260125123045</ar:FchProceso>
          <ar:CantReg>1</ar:CantReg>
          <ar:Resultado>A</ar:Resultado>
        </ar:FeCabResp>
      </ar:FECAEARegInformativoResult>
    </ar:FECAEARegInformativoResponse>
  </soap-env:Body>
</soap-env:Envelope>
""",
    ),
    (
        "/wsfe/caea/sin-movimiento/consultar",
        {
            "Cuit": 30740253022,
            "PtoVta": 1,
            "CAEA": "61234567890123",
        },
        """<?xml version="1.0" encoding="utf-8"?>
<soap-env:Envelope xmlns:soap-env="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ar="http://ar.gov.afip.dif.FEV1/">
  <soap-env:Body>
    <ar:FECAEASinMovimientoConsultarResponse>
      <ar:FECAEASinMovimientoConsultarResult>
        <ar:ResultGet>
          <ar:FECAEASinMov>
            <ar:CAEA>61234567890123</ar:CAEA>
            <ar:PtoVta>1</ar:PtoVta>
          </ar:FECAEASinMov>
        </ar:ResultGet>
      </ar:FECAEASinMovimientoConsultarResult>
    </ar:FECAEASinMovimientoConsultarResponse>
  </soap-env:Body>
</soap-env:Envelope>
""",
    ),
    (
        "/wsfe/caea/sin-movimiento/informar",
        {
            "Cuit": 30740253022,
            "PtoVta": 1,
            "CAEA": "61234567890123",
        },
        """<?xml version="1.0" encoding="utf-8"?>
<soap-env:Envelope xmlns:soap-env="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ar="http://ar.gov.afip.dif.FEV1/">
  <soap-env:Body>
    <ar:FECAEASinMovimientoInformarResponse>
      <ar:FECAEASinMovimientoInformarResult>
        <ar:CAEA>61234567890123</ar:CAEA>
        <ar:PtoVta>1</ar:PtoVta>
        <ar:Resultado>A</ar:Resultado>
      </ar:FECAEASinMovimientoInformarResult>
    </ar:FECAEASinMovimientoInformarResponse>
  </soap-env:Body>
</soap-env:Envelope>
""",
    ),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint,payload,soap_response", REQUESTS_AND_RESPONSES)
async def test_wsfe_caea_success(
    client: AsyncClient,
    wsfe_httpserver_fixed_port,
    wsfe_manager,
    override_auth,
    endpoint,
    payload,
    soap_response,
):
    wsfe_httpserver_fixed_port.expect_request("/soap", method="POST").respond_with_data(
        soap_response, content_type="text/xml"
    )

    resp = await client.post(endpoint, json=payload)

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"


@pytest.mark.asyncio
async def test_wsfe_caea_solicitar_error(client: AsyncClient, wsfe_httpserver_fixed_port, wsfe_manager, override_auth):
    wsfe_httpserver_fixed_port.expect_request("/not_existent", method="POST").respond_with_data(
        "Internal Server Error",
        status=500,
        content_type="text/plain",
    )

    payload = {
        "Cuit": 30740253022,
        "Periodo": 202601,
        "Orden": 1,
    }

    resp = await client.post("/wsfe/caea/solicitar", json=payload)

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "error"
    assert data["error"]["error_type"] == "HTTP Error"
