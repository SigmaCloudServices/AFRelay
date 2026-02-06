from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, Response

router = APIRouter()

UI_DIR = Path(__file__).resolve().parent.parent / "ui"


def _read_ui_file(file_name: str) -> str:
    return (UI_DIR / file_name).read_text(encoding="utf-8")


@router.get("/monitor/")
async def monitor_index() -> HTMLResponse:
    return HTMLResponse(content=_read_ui_file("index.html"))


@router.get("/monitor")
async def monitor_index_redirect() -> HTMLResponse:
    return HTMLResponse(content=_read_ui_file("index.html"))


@router.get("/monitor/styles.css")
async def monitor_css() -> Response:
    return Response(content=_read_ui_file("styles.css"), media_type="text/css")


@router.get("/monitor/app.js")
async def monitor_js() -> Response:
    return Response(
        content=_read_ui_file("app.js"),
        media_type="application/javascript",
    )


@router.get("/monitor/logs")
async def monitor_logs() -> HTMLResponse:
    return HTMLResponse(content=_read_ui_file("logs.html"))


@router.get("/monitor/logs.js")
async def monitor_logs_js() -> Response:
    return Response(
        content=_read_ui_file("logs.js"),
        media_type="application/javascript",
    )
