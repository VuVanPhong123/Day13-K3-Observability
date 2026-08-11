from __future__ import annotations

import re
import time
import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from structlog.contextvars import bind_contextvars, clear_contextvars


REQUEST_ID_PATTERN = re.compile(r"^req-[0-9a-f]{8}$")


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # BaseHTTPMiddleware can reuse the same worker for many requests.  Clear
        # the previous request's context before binding the new correlation ID.
        clear_contextvars()

        supplied_id = request.headers.get("x-request-id", "").strip()
        correlation_id = (
            supplied_id
            if REQUEST_ID_PATTERN.fullmatch(supplied_id)
            else f"req-{uuid.uuid4().hex[:8]}"
        )

        bind_contextvars(correlation_id=correlation_id)
        request.state.correlation_id = correlation_id

        start = time.perf_counter()
        try:
            response = await call_next(request)
            elapsed_ms = (time.perf_counter() - start) * 1000
            response.headers["x-request-id"] = correlation_id
            response.headers["x-response-time-ms"] = f"{elapsed_ms:.2f}"
            return response
        finally:
            # Do not let request metadata leak into the next request handled by
            # this worker, including when the endpoint raises an exception.
            clear_contextvars()
