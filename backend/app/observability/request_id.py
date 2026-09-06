"""Correlation-ID middleware.

Every request gets a request id (from the inbound `X-Request-ID` or a fresh
one), bound to structlog's contextvars so every log line in that request —
and the SQL, LLM, and workflow logs it triggers — carries the same id. Echoed
back in the response header so a client can quote it in a bug report.
"""

import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

HEADER = "X-Request-ID"


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get(HEADER) or uuid.uuid4().hex
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)
        response = await call_next(request)
        response.headers[HEADER] = request_id
        return response
