import pytest
from httpx import AsyncClient

SOAP_RESPONSE = """
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ns2="http://a5.soap.ws.server.puc.sr/">
    <soap:Body>
        <ns2:getPersonaResponse>
            <personaReturn>
                <datosGenerales>
                    <apellido>PEREZ</apellido>
                    <estadoClave>ACTIVO</estadoClave>
                    <idPersona>20111111112</idPersona>
                    <nombre>JUAN</nombre>
                    <tipoClave>CUIT</tipoClave>
                    <tipoPersona>FISICA</tipoPersona>
                </datosGenerales>
                <metadata>
                    <fechaHora>2026-01-07T12:00:00.000-03:00</fechaHora>
                    <servidor>srv1</servidor>
                </metadata>
            </personaReturn>
        </ns2:getPersonaResponse>
    </soap:Body>
</soap:Envelope>
"""


@pytest.mark.asyncio
async def test_get_persona_success(client: AsyncClient, wspci_httpserver_fixed_port, wspci_manager, override_auth):

    # Configure http server
    wspci_httpserver_fixed_port.expect_request("/soap", method="POST").respond_with_data(
        SOAP_RESPONSE, content_type="text/xml"
    )

    payload = {
        "cuitRepresentada": 30740253022,
        "idPersona": 20111111112
    }

    # Fastapi endpoint call
    resp = await client.post("/wspci/persona", json=payload)

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"


# Generic error only for test the API behavior in error cases. Exceptions are already tested in unit tests.
@pytest.mark.asyncio
async def test_get_persona_error(client: AsyncClient, wspci_httpserver_fixed_port, wspci_manager, override_auth):

    # Configure http server
    wspci_httpserver_fixed_port.expect_request("/not_existent", method="POST").respond_with_data(
        "Internal Server Error",
        status=500,
        content_type="text/plain",
    )

    payload = {
        "cuitRepresentada": 30740253022,
        "idPersona": 20111111112
    }

    # Fastapi endpoint call
    resp = await client.post("/wspci/persona", json=payload)

    assert resp.status_code == 200  # 200 its for FastAPI endpoint
    data = resp.json()
    assert data["status"] == "error"
    assert data["error"]["error_type"] == "HTTP Error"
