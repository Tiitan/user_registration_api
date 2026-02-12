"""Request and correlation ID context propagation middleware."""

from __future__ import annotations

from contextvars import ContextVar, Token
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

REQUEST_ID_HEADER = "X-Request-ID"
CORRELATION_ID_HEADER = "X-Correlation-ID"

_request_id_var: ContextVar[str] = ContextVar("request_id", default="-")
_correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="-")


def get_request_id() -> str:
    """Return the request ID for the current context."""
    return _request_id_var.get()


def get_correlation_id() -> str:
    """Return the correlation ID for the current context."""
    return _correlation_id_var.get()


def _resolve_id(value: str | None) -> str:
    """Return a trimmed ID value or generate one when missing."""
    if value is None:
        return str(uuid4())
    stripped = value.strip()
    return stripped or str(uuid4())


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Populate request IDs in contextvars, state, and response headers."""

    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[override]
        """Attach request IDs for the request lifecycle."""
        request_id = _resolve_id(request.headers.get(REQUEST_ID_HEADER))
        correlation_id = _resolve_id(request.headers.get(CORRELATION_ID_HEADER))

        request_id_token: Token[str] = _request_id_var.set(request_id)
        correlation_id_token: Token[str] = _correlation_id_var.set(correlation_id)
        request.state.request_id = request_id
        request.state.correlation_id = correlation_id

        try:
            response = await call_next(request)
        finally:
            _request_id_var.reset(request_id_token)
            _correlation_id_var.reset(correlation_id_token)

        response.headers[REQUEST_ID_HEADER] = request_id
        response.headers[CORRELATION_ID_HEADER] = correlation_id
        return response
