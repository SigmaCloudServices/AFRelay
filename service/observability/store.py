import math
import os
from collections import Counter, deque
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any

from service.observability.models import DomainEventEntry, RequestLogEntry


def _dt_to_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat()


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = max(0, min(len(ordered) - 1, math.ceil(p * len(ordered)) - 1))
    return ordered[idx]


class ObservabilityStore:
    def __init__(self, max_logs: int = 5000, max_events: int = 2000) -> None:
        self._request_logs: deque[RequestLogEntry] = deque(maxlen=max_logs)
        self._domain_events: deque[DomainEventEntry] = deque(maxlen=max_events)
        self._token_status: dict[str, dict[str, Any]] = {}
        self._lock = Lock()

    @classmethod
    def from_env(cls) -> "ObservabilityStore":
        max_logs = int(os.getenv("OBS_MAX_LOGS", "5000"))
        max_events = int(os.getenv("OBS_MAX_EVENTS", "2000"))
        return cls(max_logs=max_logs, max_events=max_events)

    def add_request_log(self, entry: RequestLogEntry) -> None:
        with self._lock:
            self._request_logs.append(entry)

    def add_domain_event(self, event: DomainEventEntry) -> None:
        with self._lock:
            self._domain_events.append(event)

    def update_token_status(self, service: str, value: dict[str, Any]) -> None:
        with self._lock:
            self._token_status[service] = value

    def get_token_status(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            return dict(self._token_status)

    def list_logs(
        self,
        page: int = 1,
        page_size: int = 50,
        endpoint: str | None = None,
        status: str | None = None,
        service: str | None = None,
        error_type: str | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            items = list(self._request_logs)

        if endpoint:
            items = [i for i in items if endpoint in i.path]
        if service:
            items = [i for i in items if i.service == service]
        if status == "ok":
            items = [i for i in items if i.ok]
        elif status == "error":
            items = [i for i in items if not i.ok]
        if error_type:
            items = [i for i in items if i.error_type == error_type]

        items = list(reversed(items))
        total = len(items)
        start = max((page - 1) * page_size, 0)
        end = start + page_size
        paged = items[start:end]

        return {
            "page": page,
            "page_size": page_size,
            "total": total,
            "items": [
                {
                    "timestamp": _dt_to_iso(i.timestamp),
                    "trace_id": i.trace_id,
                    "method": i.method,
                    "path": i.path,
                    "status_code": i.status_code,
                    "ok": i.ok,
                    "duration_ms": round(i.duration_ms, 3),
                    "service": i.service,
                    "error_type": i.error_type,
                    "cuit": i.cuit,
                }
                for i in paged
            ],
        }

    def get_summary(self, window_minutes: int = 60) -> dict[str, Any]:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)
        with self._lock:
            items = [i for i in self._request_logs if i.timestamp >= cutoff]

        total = len(items)
        errors = sum(1 for i in items if not i.ok)
        durations = [i.duration_ms for i in items]

        by_service: dict[str, dict[str, Any]] = {}
        for service_name in ("wsfe", "wsaa", "wspci", "ui", "health", "other"):
            service_rows = [i for i in items if i.service == service_name]
            service_total = len(service_rows)
            service_errors = sum(1 for i in service_rows if not i.ok)
            by_service[service_name] = {
                "requests": service_total,
                "errors": service_errors,
                "error_rate": round((service_errors / service_total), 4) if service_total else 0.0,
            }

        return {
            "window_minutes": window_minutes,
            "total_requests": total,
            "error_count": errors,
            "error_rate": round((errors / total), 4) if total else 0.0,
            "p95_ms": round(_percentile(durations, 0.95), 3),
            "avg_ms": round((sum(durations) / total), 3) if total else 0.0,
            "services": by_service,
        }

    def get_errors(self, window_minutes: int = 60, group_by: str = "error_type") -> dict[str, Any]:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)
        with self._lock:
            items = [i for i in self._request_logs if i.timestamp >= cutoff and not i.ok]

        grouped: Counter[str] = Counter()
        last_seen: dict[str, datetime] = {}
        sample: dict[str, str | None] = {}
        for item in items:
            key = item.error_type or f"HTTP_{item.status_code}" if group_by == "error_type" else item.path
            grouped[key] += 1
            last_seen[key] = max(last_seen.get(key, item.timestamp), item.timestamp)
            sample[key] = item.path if group_by == "error_type" else item.error_type

        rows = [
            {
                "key": key,
                "count": count,
                "last_seen": _dt_to_iso(last_seen[key]),
                "sample": sample.get(key),
            }
            for key, count in grouped.most_common()
        ]
        return {"window_minutes": window_minutes, "group_by": group_by, "items": rows}

    def get_operations_summary(self, window_minutes: int = 60) -> dict[str, Any]:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)
        with self._lock:
            logs = [i for i in self._request_logs if i.timestamp >= cutoff]
            events = [e for e in self._domain_events if e.timestamp >= cutoff]

        def _count(path: str, ok: bool | None = None) -> int:
            rows = [i for i in logs if i.path == path]
            if ok is None:
                return len(rows)
            return sum(1 for i in rows if i.ok == ok)

        caea_paths = [
            "/wsfe/caea/solicitar",
            "/wsfe/caea/consultar",
            "/wsfe/caea/informar",
            "/wsfe/caea/sin-movimiento/consultar",
            "/wsfe/caea/sin-movimiento/informar",
        ]
        caea_counts = {path.split("/wsfe/caea/")[1]: _count(path) for path in caea_paths}
        domain_event_counts = Counter(e.event_type for e in events)
        domain_error_counts = Counter(
            f"{e.event_type}:{e.error_type}" for e in events if e.status == "error" and e.error_type
        )

        return {
            "window_minutes": window_minutes,
            "fecae": {
                "success": _count("/wsfe/invoices", ok=True),
                "error": _count("/wsfe/invoices", ok=False),
            },
            "last_authorized": {
                "success": _count("/wsfe/invoices/last-authorized", ok=True),
                "error": _count("/wsfe/invoices/last-authorized", ok=False),
            },
            "invoice_query": {
                "success": _count("/wsfe/invoices/query", ok=True),
                "error": _count("/wsfe/invoices/query", ok=False),
            },
            "wsfe_params": {
                "max_reg_x_request": {
                    "success": _count("/wsfe/params/max-reg-x-request", ok=True),
                    "error": _count("/wsfe/params/max-reg-x-request", ok=False),
                },
                "types_cbte": {
                    "success": _count("/wsfe/params/types-cbte", ok=True),
                    "error": _count("/wsfe/params/types-cbte", ok=False),
                },
                "types_doc": {
                    "success": _count("/wsfe/params/types-doc", ok=True),
                    "error": _count("/wsfe/params/types-doc", ok=False),
                },
                "types_iva": {
                    "success": _count("/wsfe/params/types-iva", ok=True),
                    "error": _count("/wsfe/params/types-iva", ok=False),
                },
                "types_tributos": {
                    "success": _count("/wsfe/params/types-tributos", ok=True),
                    "error": _count("/wsfe/params/types-tributos", ok=False),
                },
                "types_monedas": {
                    "success": _count("/wsfe/params/types-monedas", ok=True),
                    "error": _count("/wsfe/params/types-monedas", ok=False),
                },
                "condicion_iva_receptor": {
                    "success": _count("/wsfe/params/condicion-iva-receptor", ok=True),
                    "error": _count("/wsfe/params/condicion-iva-receptor", ok=False),
                },
                "puntos_venta": {
                    "success": _count("/wsfe/params/puntos-venta", ok=True),
                    "error": _count("/wsfe/params/puntos-venta", ok=False),
                },
                "cotizacion": {
                    "success": _count("/wsfe/params/cotizacion", ok=True),
                    "error": _count("/wsfe/params/cotizacion", ok=False),
                },
                "types_concepto": {
                    "success": _count("/wsfe/params/types-concepto", ok=True),
                    "error": _count("/wsfe/params/types-concepto", ok=False),
                },
                "types_opcional": {
                    "success": _count("/wsfe/params/types-opcional", ok=True),
                    "error": _count("/wsfe/params/types-opcional", ok=False),
                },
                "types_paises": {
                    "success": _count("/wsfe/params/types-paises", ok=True),
                    "error": _count("/wsfe/params/types-paises", ok=False),
                },
                "actividades": {
                    "success": _count("/wsfe/params/actividades", ok=True),
                    "error": _count("/wsfe/params/actividades", ok=False),
                },
            },
            "caea": caea_counts,
            "domain_events": {
                "by_type": dict(domain_event_counts),
                "error_signatures": dict(domain_error_counts),
            },
        }

    def list_domain_events(
        self,
        page: int = 1,
        page_size: int = 50,
        service: str | None = None,
        event_type: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            items = list(self._domain_events)

        if service:
            items = [i for i in items if i.service == service]
        if event_type:
            items = [i for i in items if i.event_type == event_type]
        if status:
            items = [i for i in items if i.status == status]

        items = list(reversed(items))
        total = len(items)
        start = max((page - 1) * page_size, 0)
        end = start + page_size
        paged = items[start:end]

        return {
            "page": page,
            "page_size": page_size,
            "total": total,
            "items": [
                {
                    "timestamp": _dt_to_iso(i.timestamp),
                    "trace_id": i.trace_id,
                    "service": i.service,
                    "event_type": i.event_type,
                    "status": i.status,
                    "entity_key": i.entity_key,
                    "error_type": i.error_type,
                    "payload": i.payload,
                }
                for i in paged
            ],
        }

    def get_alerts(self) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        active: list[dict[str, Any]] = []

        summary_10m = self.get_summary(window_minutes=10)
        if summary_10m["total_requests"] >= 20 and summary_10m["error_rate"] >= 0.2:
            active.append(
                {
                    "rule_id": "high_error_rate_10m",
                    "severity": "high",
                    "title": "High error rate in last 10 minutes",
                    "detail": summary_10m,
                }
            )

        errors_15m = self.get_errors(window_minutes=15, group_by="error_type")
        if errors_15m["items"] and errors_15m["items"][0]["count"] >= 5:
            active.append(
                {
                    "rule_id": "repeated_error_signature",
                    "severity": "medium",
                    "title": "Repeated error signature detected",
                    "detail": errors_15m["items"][0],
                }
            )

        token_state = self.get_token_status()
        for service, state in token_state.items():
            expires_at_str = state.get("expires_at")
            if not expires_at_str:
                continue
            try:
                expires_at = datetime.fromisoformat(expires_at_str)
            except ValueError:
                continue
            if expires_at - now <= timedelta(minutes=30):
                active.append(
                    {
                        "rule_id": f"{service}_token_expiring",
                        "severity": "high",
                        "title": f"{service.upper()} token expires soon",
                        "detail": state,
                    }
                )

        return {"active": active, "count": len(active)}
