"""Trace ID middleware and request logging.

Each request gets a fresh 21-char nanoid traceId. It is:
  - stored in a contextvar so structlog includes it in every log entry
  - returned in the ``X-Trace-Id`` response header
  - included in every error envelope under the ``traceId`` field
"""
from __future__ import annotations

import time
from contextvars import ContextVar

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from pandamind.core.ids import generate_id

trace_id_var: ContextVar[str] = ContextVar("trace_id", default="-")


class TraceIdMiddleware(BaseHTTPMiddleware):
    """Attach a server-generated trace id to every request and response."""

    async def dispatch(self, request: Request, call_next) -> Response:
        trace_id = generate_id()
        token = trace_id_var.set(trace_id)

        structlog.contextvars.bind_contextvars(
            trace_id=trace_id,
            method=request.method,
            path=request.url.path,
        )

        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.perf_counter() - start) * 1000
            structlog.get_logger().exception(
                "request.failed", duration_ms=round(duration_ms, 2)
            )
            raise
        finally:
            structlog.contextvars.clear_contextvars()
            trace_id_var.reset(token)

        duration_ms = (time.perf_counter() - start) * 1000
        response.headers["X-Trace-Id"] = trace_id
        structlog.get_logger().info(
            "request.completed",
            status_code=response.status_code,
            duration_ms=round(duration_ms, 2),
        )
        return response


def get_current_trace_id() -> str:
    """Return the trace id for the current request, or '-' outside a request."""
    return trace_id_var.get()
