import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_monitor_index_served(client: AsyncClient):
    resp = await client.get("/monitor/")
    assert resp.status_code == 200
    assert "AFRelay Monitor" in resp.text
    assert "Logs & Events" in resp.text
    assert "CAEA Assignments by POS" in resp.text
    assert "POS List" in resp.text
    assert "WSFE POS List" in resp.text
    assert "WSFE New Params Snapshot" in resp.text
    assert "CbteNro (query)" in resp.text


@pytest.mark.asyncio
async def test_monitor_assets_served(client: AsyncClient):
    css_resp = await client.get("/monitor/styles.css")
    js_resp = await client.get("/monitor/app.js")
    logs_html = await client.get("/monitor/logs")
    logs_js = await client.get("/monitor/logs.js")

    assert css_resp.status_code == 200
    assert js_resp.status_code == 200
    assert logs_html.status_code == 200
    assert logs_js.status_code == 200
    assert "--accent" in css_resp.text
    assert "refreshAll" in js_resp.text
    assert "activateTab" in js_resp.text
    assert "refreshWsfePosParams" in js_resp.text
    assert "refreshWsfeParamsSnapshot" in js_resp.text
    assert "/wsfe/invoices/last-authorized" in js_resp.text
    assert "/wsfe/params/puntos-venta" in js_resp.text
    assert "renderAssignments" in js_resp.text
    assert "renderPosList" in js_resp.text
    assert "AFRelay Logs" in logs_html.text
    assert "refreshLogs" in logs_js.text
