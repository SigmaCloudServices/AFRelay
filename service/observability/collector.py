import json
import uuid
import xml.etree.ElementTree as ET
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.paths import get_afip_paths
from service.observability.models import DomainEventEntry, RequestLogEntry
from service.observability.store import ObservabilityStore

_store = ObservabilityStore.from_env()
_trace_id_context: ContextVar[str | None] = ContextVar("trace_id", default=None)


def get_store() -> ObservabilityStore:
    return _store


def new_trace_id() -> str:
    return uuid.uuid4().hex


def set_current_trace_id(trace_id: str | None):
    return _trace_id_context.set(trace_id)


def reset_current_trace_id(token) -> None:
    _trace_id_context.reset(token)


def get_current_trace_id() -> str | None:
    return _trace_id_context.get()


def infer_service(path: str) -> str:
    if path.startswith("/wsfe"):
        return "wsfe"
    if path.startswith("/wsaa"):
        return "wsaa"
    if path.startswith("/wspci"):
        return "wspci"
    if path.startswith("/ui"):
        return "ui"
    if path.startswith("/health"):
        return "health"
    return "other"


def _parse_json_body(raw_body: bytes | None) -> dict[str, Any] | None:
    if not raw_body:
        return None
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _extract_cuit(request_payload: dict[str, Any] | None) -> int | None:
    if not request_payload:
        return None
    cuit = request_payload.get("Cuit")
    if isinstance(cuit, int):
        return cuit
    auth = request_payload.get("Auth")
    if isinstance(auth, dict) and isinstance(auth.get("Cuit"), int):
        return auth["Cuit"]
    return None


def record_http_exchange(
    *,
    method: str,
    path: str,
    status_code: int,
    duration_ms: float,
    trace_id: str,
    request_body: bytes | None = None,
    response_body: bytes | None = None,
) -> None:
    request_payload = _parse_json_body(request_body)
    response_payload = _parse_json_body(response_body)

    ok = status_code < 400
    error_type = None
    if response_payload and response_payload.get("status") == "error":
        ok = False
        error_obj = response_payload.get("error")
        if isinstance(error_obj, dict):
            error_type = error_obj.get("error_type")
    if not ok and not error_type:
        error_type = f"HTTP_{status_code}"

    service = infer_service(path)
    _store.add_request_log(
        RequestLogEntry(
            trace_id=trace_id,
            method=method,
            path=path,
            status_code=status_code,
            ok=ok,
            duration_ms=duration_ms,
            service=service,
            error_type=error_type,
            cuit=_extract_cuit(request_payload),
        )
    )

    if path.startswith("/wsfe/caea"):
        emit_domain_event(
            event_type="wsfe_caea_http_call",
            service="wsfe",
            status="success" if ok else "error",
            entity_key=path,
            error_type=error_type,
        )
    elif path == "/wsfe/invoices":
        emit_domain_event(
            event_type="wsfe_fecae_http_call",
            service="wsfe",
            status="success" if ok else "error",
            entity_key="fecae",
            error_type=error_type,
        )
    elif path in ("/wsaa/token", "/wspci/token"):
        refresh_token_state_from_files()
        emit_domain_event(
            event_type="token_renew_http_call",
            service=infer_service(path),
            status="success" if ok else "error",
            entity_key=path,
            error_type=error_type,
        )


def emit_domain_event(
    *,
    event_type: str,
    service: str,
    status: str,
    entity_key: str | None = None,
    payload: dict[str, Any] | None = None,
    error_type: str | None = None,
) -> None:
    _store.add_domain_event(
        DomainEventEntry(
            event_type=event_type,
            service=service,
            status=status,
            trace_id=get_current_trace_id(),
            entity_key=entity_key,
            payload=payload,
            error_type=error_type,
        )
    )


def _parse_token_xml(path: Path) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    if not path.exists():
        return {"valid": False, "expires_at": None, "last_error": "token_file_not_found"}

    try:
        root = ET.parse(path).getroot()
        expiration_node = root.find(".//expirationTime")
        if expiration_node is None or not expiration_node.text:
            return {"valid": False, "expires_at": None, "last_error": "missing_expiration_time"}
        expiration = datetime.fromisoformat(expiration_node.text)
        return {
            "valid": now < expiration,
            "expires_at": expiration.astimezone(timezone.utc).isoformat(),
            "last_error": None,
        }
    except Exception as exc:  # pragma: no cover - defensive.
        return {"valid": False, "expires_at": None, "last_error": str(exc)}


def refresh_token_state_from_files() -> dict[str, dict[str, Any]]:
    paths = get_afip_paths()
    wsaa_data = _parse_token_xml(paths.login_response)
    wspci_data = _parse_token_xml(paths.wspci_login_response)

    now_iso = datetime.now(timezone.utc).isoformat()
    wsaa_data["checked_at"] = now_iso
    wspci_data["checked_at"] = now_iso
    _store.update_token_status("wsaa", wsaa_data)
    _store.update_token_status("wspci", wspci_data)

    return {"wsaa": wsaa_data, "wspci": wspci_data}
