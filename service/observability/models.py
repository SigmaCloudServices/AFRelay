from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class RequestLogEntry:
    trace_id: str
    method: str
    path: str
    status_code: int
    ok: bool
    duration_ms: float
    service: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    error_type: str | None = None
    cuit: int | None = None


@dataclass
class DomainEventEntry:
    event_type: str
    service: str
    status: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    trace_id: str | None = None
    error_type: str | None = None
    entity_key: str | None = None
    payload: dict[str, Any] | None = None
