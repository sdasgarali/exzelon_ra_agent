"""Security headers middleware.

Adds standard security headers to every HTTP response to protect against
common web vulnerabilities (clickjacking, MIME sniffing, XSS, etc.).
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


# Endpoints where CSP is skipped because Swagger UI requires inline scripts/styles
_DOCS_PATHS = frozenset({"/docs", "/redoc", "/openapi.json"})

_CSP_VALUE = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: https:; "
    "font-src 'self' data:; "
    "connect-src 'self' https:;"
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Starlette middleware that injects security headers into every response."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        # --- Always-on headers ---
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=()"
        )

        # --- HSTS: only when the connection is (or was) over TLS ---
        scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
        if scheme == "https":
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )

        # --- CSP: skip for API docs endpoints (Swagger UI needs inline scripts) ---
        if request.url.path not in _DOCS_PATHS:
            response.headers["Content-Security-Policy"] = _CSP_VALUE

        return response
