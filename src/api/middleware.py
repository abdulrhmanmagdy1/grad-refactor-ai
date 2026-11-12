"""FastAPI middleware for safety, security headers, request tracing and exception handling.

NFR01/NFR02 are enforced here (body-size limit, defensive security headers);
every response additionally carries an ``X-Request-ID`` and a timing header so
a run shown in the UI can be traced to the exact server log line that produced
it without any third-party tooling.
"""

import logging
import re
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger("refactor_ai.api")

MAX_REQUEST_BYTES = 100_000
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

# Content-Security-Policy for the bundled single-page client.
#
# The interface is served from the same origin and loads no third-party code:
# the editor and its workers come from the local bundle, so the policy can stay
# strict (`script-src 'self'`). Monaco injects styles at runtime and starts its
# language workers from blob URLs, which is why those two sources are allowed
# explicitly and nothing else is.
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; "
    "font-src 'self' data:; "
    "worker-src 'self' blob:; "
    "connect-src 'self'; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "frame-ancestors 'none'"
)

PERMISSIONS_POLICY = "camera=(), microphone=(), geolocation=(), payment=()"


def _request_id(request: Request) -> str:
    """Reuse a well-formed caller request id, otherwise mint a fresh one."""
    incoming = request.headers.get("x-request-id", "")
    if _REQUEST_ID_PATTERN.fullmatch(incoming):
        return incoming
    return uuid.uuid4().hex


def _payload_too_large(request: Request) -> bool:
    """Reject oversized requests from the declared body size before parsing."""
    content_length = request.headers.get("content-length")
    if not content_length:
        return False
    try:
        return int(content_length) > MAX_REQUEST_BYTES
    except ValueError:
        return False  # Malformed header; let the framework handle parsing.


def _log_request(request: Request, status_code: int, elapsed_ms: float, request_id: str) -> None:
    """Log API traffic at INFO and static-asset noise at DEBUG.

    The structured extras (``request_id``, ``status``, ``duration_ms``) make the
    line machine-readable: a run shown in the interface can be traced to the
    exact request that produced it (ADR16).
    """
    extra = {
        "request_id": request_id,
        "status": status_code,
        "duration_ms": round(elapsed_ms, 2),
        "method": request.method,
        "path": request.url.path,
    }
    if request.url.path.startswith(("/runs", "/api/", "/health")):
        logger.info(
            "%s %s -> %s in %.1fms",
            request.method,
            request.url.path,
            status_code,
            elapsed_ms,
            extra=extra,
        )
    else:
        logger.debug(
            "%s %s -> %s in %.1fms",
            request.method,
            request.url.path,
            status_code,
            elapsed_ms,
            extra=extra,
        )


class SecurityAndLimitsMiddleware(BaseHTTPMiddleware):
    """Enforces request limits and attaches tracing plus security headers."""

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = _request_id(request)
        started = time.perf_counter()

        response: Response
        if _payload_too_large(request):
            response = JSONResponse(
                status_code=413,
                content={"detail": "Payload too large. Maximum request size is 100KB."},
            )
        else:
            try:
                response = await call_next(request)
            except Exception as exc:
                logger.exception(
                    "Unhandled server exception: %s",
                    exc,
                    extra={
                        "request_id": request_id,
                        "method": request.method,
                        "path": request.url.path,
                    },
                )
                response = JSONResponse(
                    status_code=500,
                    content={
                        "error": "Internal server error occurred.",
                        "detail": str(exc),
                    },
                )

        elapsed_ms = (time.perf_counter() - started) * 1000
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time-Ms"] = f"{elapsed_ms:.1f}"

        # Standard defense-in-depth security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = CONTENT_SECURITY_POLICY
        response.headers["Permissions-Policy"] = PERMISSIONS_POLICY

        _log_request(request, response.status_code, elapsed_ms, request_id)
        return response
