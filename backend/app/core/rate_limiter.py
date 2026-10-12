"""Shared rate limiter instance for all API endpoints.

Uses slowapi with IP-based key function. Import `limiter` from here
in any endpoint module that needs rate limiting.

Storage: in-process memory by default, which is per worker and resets on
restart — so an N-worker deployment effectively allows N x the limit (e.g. on
/auth/signup). Set ``RATE_LIMIT_STORAGE_URI`` (e.g. to the Redis URL) to share
counters across workers. If that backend is unreachable at request time,
slowapi falls back to memory instead of failing requests.
"""
import logging

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings

logger = logging.getLogger(__name__)


def _storage_uri() -> str:
    uri = (getattr(settings, "RATE_LIMIT_STORAGE_URI", "") or "").strip()
    return uri or "memory://"


_STORAGE_URI = _storage_uri()

limiter = Limiter(
    key_func=get_remote_address,
    swallow_errors=True,
    storage_uri=_STORAGE_URI,
    in_memory_fallback_enabled=_STORAGE_URI != "memory://",
)

if _STORAGE_URI != "memory://":
    logger.info("Rate limiter using shared storage: %s", _STORAGE_URI.split("@")[-1])
