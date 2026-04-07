"""Middleware package for the FastAPI application."""

from app.middleware.security_headers import SecurityHeadersMiddleware

__all__ = ["SecurityHeadersMiddleware"]
