import time

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from service.observability.collector import (new_trace_id, record_http_exchange,
                                             reset_current_trace_id,
                                             set_current_trace_id)


class ObservabilityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/monitor"):
            return await call_next(request)

        trace_id = new_trace_id()
        trace_ctx_token = set_current_trace_id(trace_id)
        raw_body = await request.body()
        pending_body = raw_body

        async def receive():
            nonlocal pending_body
            body = pending_body
            pending_body = b""
            return {"type": "http.request", "body": body, "more_body": False}

        request = Request(request.scope, receive)
        request.state.trace_id = trace_id

        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.perf_counter() - started) * 1000.0
            record_http_exchange(
                method=request.method,
                path=request.url.path,
                status_code=500,
                duration_ms=duration_ms,
                trace_id=trace_id,
                request_body=raw_body,
                response_body=None,
            )
            reset_current_trace_id(trace_ctx_token)
            raise

        duration_ms = (time.perf_counter() - started) * 1000.0
        response_body = getattr(response, "body", None)
        record_http_exchange(
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
            trace_id=trace_id,
            request_body=raw_body,
            response_body=response_body,
        )
        response.headers["X-Trace-Id"] = trace_id
        reset_current_trace_id(trace_ctx_token)
        return response
