import pytest
from httpx import AsyncClient


SOAP_RESPONSES = {
    "/wsfe/params/max-reg-x-request": """<?xml version="1.0" encoding="utf-8"?>
<soap-env:Envelope xmlns:soap-env="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ar="http://ar.gov.afip.dif.FEV1/">
  <soap-env:Header/>
  <soap-env:Body>
    <ar:FECompTotXRequestResponse>
      <ar:FECompTotXRequestResult>
        <ar:RegXReq>1000</ar:RegXReq>
      </ar:FECompTotXRequestResult>
    </ar:FECompTotXRequestResponse>
  </soap-env:Body>
</soap-env:Envelope>
""",
    "/wsfe/params/types-cbte": """<?xml version="1.0" encoding="utf-8"?>
<soap-env:Envelope xmlns:soap-env="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ar="http://ar.gov.afip.dif.FEV1/">
  <soap-env:Body>
    <ar:FEParamGetTiposCbteResponse>
      <ar:FEParamGetTiposCbteResult>
        <ar:ResultGet>
          <ar:CbteTipo>
            <ar:Id>1</ar:Id>
            <ar:Desc>Factura A</ar:Desc>
          </ar:CbteTipo>
        </ar:ResultGet>
      </ar:FEParamGetTiposCbteResult>
    </ar:FEParamGetTiposCbteResponse>
  </soap-env:Body>
</soap-env:Envelope>
""",
    "/wsfe/params/types-doc": """<?xml version="1.0" encoding="utf-8"?>
<soap-env:Envelope xmlns:soap-env="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ar="http://ar.gov.afip.dif.FEV1/">
  <soap-env:Body>
    <ar:FEParamGetTiposDocResponse>
      <ar:FEParamGetTiposDocResult>
        <ar:ResultGet>
          <ar:DocTipo>
            <ar:Id>80</ar:Id>
            <ar:Desc>CUIT</ar:Desc>
          </ar:DocTipo>
        </ar:ResultGet>
      </ar:FEParamGetTiposDocResult>
    </ar:FEParamGetTiposDocResponse>
  </soap-env:Body>
</soap-env:Envelope>
""",
    "/wsfe/params/types-iva": """<?xml version="1.0" encoding="utf-8"?>
<soap-env:Envelope xmlns:soap-env="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ar="http://ar.gov.afip.dif.FEV1/">
  <soap-env:Body>
    <ar:FEParamGetTiposIvaResponse>
      <ar:FEParamGetTiposIvaResult>
        <ar:ResultGet>
          <ar:IvaTipo>
            <ar:Id>5</ar:Id>
            <ar:Desc>21%</ar:Desc>
          </ar:IvaTipo>
        </ar:ResultGet>
      </ar:FEParamGetTiposIvaResult>
    </ar:FEParamGetTiposIvaResponse>
  </soap-env:Body>
</soap-env:Envelope>
""",
    "/wsfe/params/types-tributos": """<?xml version="1.0" encoding="utf-8"?>
<soap-env:Envelope xmlns:soap-env="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ar="http://ar.gov.afip.dif.FEV1/">
  <soap-env:Body>
    <ar:FEParamGetTiposTributosResponse>
      <ar:FEParamGetTiposTributosResult>
        <ar:ResultGet>
          <ar:TributoTipo>
            <ar:Id>1</ar:Id>
            <ar:Desc>Impuestos nacionales</ar:Desc>
          </ar:TributoTipo>
        </ar:ResultGet>
      </ar:FEParamGetTiposTributosResult>
    </ar:FEParamGetTiposTributosResponse>
  </soap-env:Body>
</soap-env:Envelope>
""",
    "/wsfe/params/types-monedas": """<?xml version="1.0" encoding="utf-8"?>
<soap-env:Envelope xmlns:soap-env="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ar="http://ar.gov.afip.dif.FEV1/">
  <soap-env:Body>
    <ar:FEParamGetTiposMonedasResponse>
      <ar:FEParamGetTiposMonedasResult>
        <ar:ResultGet>
          <ar:Moneda>
            <ar:Id>PES</ar:Id>
            <ar:Desc>Peso Argentino</ar:Desc>
          </ar:Moneda>
        </ar:ResultGet>
      </ar:FEParamGetTiposMonedasResult>
    </ar:FEParamGetTiposMonedasResponse>
  </soap-env:Body>
</soap-env:Envelope>
""",
    "/wsfe/params/condicion-iva-receptor": """<?xml version="1.0" encoding="utf-8"?>
<soap-env:Envelope xmlns:soap-env="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ar="http://ar.gov.afip.dif.FEV1/">
  <soap-env:Body>
    <ar:FEParamGetCondicionIvaReceptorResponse>
      <ar:FEParamGetCondicionIvaReceptorResult>
        <ar:ResultGet>
          <ar:CondicionIvaReceptor>
            <ar:Id>5</ar:Id>
            <ar:Desc>Consumidor Final</ar:Desc>
            <ar:Cmp_Clase>A/M/C</ar:Cmp_Clase>
          </ar:CondicionIvaReceptor>
        </ar:ResultGet>
      </ar:FEParamGetCondicionIvaReceptorResult>
    </ar:FEParamGetCondicionIvaReceptorResponse>
  </soap-env:Body>
</soap-env:Envelope>
""",
    "/wsfe/params/puntos-venta": """<?xml version="1.0" encoding="utf-8"?>
<soap-env:Envelope xmlns:soap-env="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ar="http://ar.gov.afip.dif.FEV1/">
  <soap-env:Body>
    <ar:FEParamGetPtosVentaResponse>
      <ar:FEParamGetPtosVentaResult>
        <ar:ResultGet>
          <ar:PtoVenta>
            <ar:Nro>1</ar:Nro>
            <ar:EmisionTipo>CAE</ar:EmisionTipo>
            <ar:Bloqueado>N</ar:Bloqueado>
          </ar:PtoVenta>
        </ar:ResultGet>
      </ar:FEParamGetPtosVentaResult>
    </ar:FEParamGetPtosVentaResponse>
  </soap-env:Body>
</soap-env:Envelope>
""",
    "/wsfe/params/cotizacion": """<?xml version="1.0" encoding="utf-8"?>
<soap-env:Envelope xmlns:soap-env="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ar="http://ar.gov.afip.dif.FEV1/">
  <soap-env:Body>
    <ar:FEParamGetCotizacionResponse>
      <ar:FEParamGetCotizacionResult>
        <ar:ResultGet>
          <ar:MonId>USD</ar:MonId>
          <ar:MonCotiz>1050.25</ar:MonCotiz>
          <ar:FchCotiz>20260203</ar:FchCotiz>
        </ar:ResultGet>
      </ar:FEParamGetCotizacionResult>
    </ar:FEParamGetCotizacionResponse>
  </soap-env:Body>
</soap-env:Envelope>
""",
    "/wsfe/params/types-concepto": """<?xml version="1.0" encoding="utf-8"?>
<soap-env:Envelope xmlns:soap-env="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ar="http://ar.gov.afip.dif.FEV1/">
  <soap-env:Body>
    <ar:FEParamGetTiposConceptoResponse>
      <ar:FEParamGetTiposConceptoResult>
        <ar:ResultGet>
          <ar:ConceptoTipo>
            <ar:Id>1</ar:Id>
            <ar:Desc>Productos</ar:Desc>
          </ar:ConceptoTipo>
        </ar:ResultGet>
      </ar:FEParamGetTiposConceptoResult>
    </ar:FEParamGetTiposConceptoResponse>
  </soap-env:Body>
</soap-env:Envelope>
""",
    "/wsfe/params/types-opcional": """<?xml version="1.0" encoding="utf-8"?>
<soap-env:Envelope xmlns:soap-env="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ar="http://ar.gov.afip.dif.FEV1/">
  <soap-env:Body>
    <ar:FEParamGetTiposOpcionalResponse>
      <ar:FEParamGetTiposOpcionalResult>
        <ar:ResultGet>
          <ar:OpcionalTipo>
            <ar:Id>2101</ar:Id>
            <ar:Desc>CBU</ar:Desc>
          </ar:OpcionalTipo>
        </ar:ResultGet>
      </ar:FEParamGetTiposOpcionalResult>
    </ar:FEParamGetTiposOpcionalResponse>
  </soap-env:Body>
</soap-env:Envelope>
""",
    "/wsfe/params/types-paises": """<?xml version="1.0" encoding="utf-8"?>
<soap-env:Envelope xmlns:soap-env="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ar="http://ar.gov.afip.dif.FEV1/">
  <soap-env:Body>
    <ar:FEParamGetTiposPaisesResponse>
      <ar:FEParamGetTiposPaisesResult>
        <ar:ResultGet>
          <ar:PaisTipo>
            <ar:Id>200</ar:Id>
            <ar:Desc>Argentina</ar:Desc>
          </ar:PaisTipo>
        </ar:ResultGet>
      </ar:FEParamGetTiposPaisesResult>
    </ar:FEParamGetTiposPaisesResponse>
  </soap-env:Body>
</soap-env:Envelope>
""",
    "/wsfe/params/actividades": """<?xml version="1.0" encoding="utf-8"?>
<soap-env:Envelope xmlns:soap-env="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ar="http://ar.gov.afip.dif.FEV1/">
  <soap-env:Body>
    <ar:FEParamGetActividadesResponse>
      <ar:FEParamGetActividadesResult>
        <ar:ResultGet>
          <ar:ActividadesTipo>
            <ar:Id>620200</ar:Id>
            <ar:Orden>1</ar:Orden>
            <ar:Desc>Servicios de consultoria informatica</ar:Desc>
          </ar:ActividadesTipo>
        </ar:ResultGet>
      </ar:FEParamGetActividadesResult>
    </ar:FEParamGetActividadesResponse>
  </soap-env:Body>
</soap-env:Envelope>
""",
}


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", list(SOAP_RESPONSES))
async def test_wsfe_params_success(client: AsyncClient, wsfe_httpserver_fixed_port, wsfe_manager, override_auth, endpoint):
    wsfe_httpserver_fixed_port.expect_request("/soap", method="POST").respond_with_data(
        SOAP_RESPONSES[endpoint], content_type="text/xml"
    )

    payload = {"Cuit": 30740253022}
    if endpoint == "/wsfe/params/condicion-iva-receptor":
        payload["ClaseCmp"] = "A/M/C"
    if endpoint == "/wsfe/params/cotizacion":
        payload["MonId"] = "USD"
        payload["FchCotiz"] = "20260203"

    resp = await client.post(endpoint, json=payload)

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"


@pytest.mark.asyncio
async def test_wsfe_param_max_reg_error(client: AsyncClient, wsfe_httpserver_fixed_port, wsfe_manager, override_auth):
    wsfe_httpserver_fixed_port.expect_request("/not_existent", method="POST").respond_with_data(
        "Internal Server Error",
        status=500,
        content_type="text/plain",
    )

    resp = await client.post("/wsfe/params/max-reg-x-request", json={"Cuit": 30740253022})

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "error"
    assert data["error"]["error_type"] == "HTTP Error"
