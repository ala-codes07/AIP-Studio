"""Request-scoped middleware: correlation IDs and access logging."""

from __future__ import annotations

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import request_id_ctx

logger = logging.getLogger("app.request")

REQUEST_ID_HEADER = "X-Request-ID"


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Attach a request ID to every request/response and emit an access log line."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())
        token = request_id_ctx.set(request_id)
        started = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception:
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            logger.exception(
                "request_failed",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "duration_ms": duration_ms,
                },
            )
            request_id_ctx.reset(token)
            raise

        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        response.headers[REQUEST_ID_HEADER] = request_id
        logger.info(
            "request_completed",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        request_id_ctx.reset(token)
        return response

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Conservative headers for same-origin dashboard + authenticated API."""
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response.headers['Permissions-Policy'] = 'geolocation=(), camera=(), microphone=()'
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; "
            "form-action 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'self'"
        )
        if request.url.path.startswith('/api/v1/auth'):
            response.headers['Cache-Control'] = 'no-store'
        from app.core.config import get_settings
        if get_settings().is_production:
            response.headers['Strict-Transport-Security'] = 'max-age=31536000'
        return response


class AuthRateLimitMiddleware(BaseHTTPMiddleware):
    """Basic local per-IP authentication throttling.

    Additional distributed edge controls are required on public deployments;
    this is defense in depth, not a replacement for a reverse-proxy limiter.
    """
    _paths = {
        '/api/v1/auth/login': 15,
        '/api/v1/auth/register': 6,
        '/api/v1/auth/forgot-password': 12,
        '/api/v1/auth/resend-verification': 12,
        '/api/v1/auth/reset-password': 20,
        '/api/v1/auth/verify-email': 20,
    }
    _window_seconds = 600

    def __init__(self, app):
        super().__init__(app)
        import threading
        from collections import deque
        self._lock = threading.Lock()
        self._attempts: dict[tuple[str, str], list[float]] = {}

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        from app.core.config import get_settings
        from starlette.responses import JSONResponse
        if not get_settings().is_production or request.method != 'POST' or request.url.path not in self._paths:
            return await call_next(request)
        key = (request.client.host if request.client else 'unknown', request.url.path)
        now = time.monotonic()
        with self._lock:
            # Evict stale keys to bound memory growth. Avoid trusting X-Forwarded-For.
            if len(self._attempts) > 6000:
                self._attempts = {k: v for k, v in self._attempts.items() if v and now - v[-1] <= self._window_seconds}
            records = [x for x in self._attempts.get(key, []) if now - x <= self._window_seconds]
            limit = self._paths[request.url.path]
            blocked = len(records) >= limit
            if not blocked:
                records.append(now)
                self._attempts[key] = records
        if blocked:
            return JSONResponse({'error': {'code':'rate_limited','message':'Too many requests. Retry in ten minutes.'}},
                                status_code=429, headers={'Retry-After':'600'})
        return await call_next(request)
