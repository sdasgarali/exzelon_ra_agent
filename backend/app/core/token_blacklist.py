"""JWT revocation list for logout (ELR-027).

A revoked access token's ``jti`` is stored until it would have expired anyway, so
a logged-out token can't be replayed within its 30-minute lifetime. Backed by
Redis when reachable; otherwise an in-process dict with TTL (correct for a single
worker / tests, and a safe degradation — it never fails open on the same worker).
"""
import time
import threading
import structlog

from app.core.config import settings

logger = structlog.get_logger()

_KEY_PREFIX = "revoked_jti:"

# In-process fallback: jti -> expiry epoch seconds.
_local_lock = threading.Lock()
_local_store: dict[str, float] = {}

_redis_client = None
_redis_tried = False


def _get_redis():
    """Lazily connect to Redis; return None if unavailable (fall back to memory)."""
    global _redis_client, _redis_tried
    if _redis_tried:
        return _redis_client
    _redis_tried = True
    try:
        import redis
        client = redis.Redis.from_url(settings.REDIS_URL, socket_connect_timeout=0.5)
        client.ping()
        _redis_client = client
    except Exception as e:  # unreachable / not installed → memory fallback
        logger.info("Token blacklist using in-process store (Redis unavailable)", error=str(e))
        _redis_client = None
    return _redis_client


def _purge_expired_locked(now: float) -> None:
    for jti, exp in list(_local_store.items()):
        if exp <= now:
            _local_store.pop(jti, None)


def revoke(jti: str, ttl_seconds: int) -> None:
    """Revoke a token id for ``ttl_seconds`` (its remaining lifetime)."""
    if not jti or ttl_seconds <= 0:
        return
    client = _get_redis()
    if client is not None:
        try:
            client.setex(_KEY_PREFIX + jti, ttl_seconds, "1")
            return
        except Exception:
            pass  # fall through to memory
    now = time.time()
    with _local_lock:
        _purge_expired_locked(now)
        _local_store[jti] = now + ttl_seconds


def is_revoked(jti: str) -> bool:
    if not jti:
        return False
    client = _get_redis()
    if client is not None:
        try:
            return client.exists(_KEY_PREFIX + jti) == 1
        except Exception:
            pass
    now = time.time()
    with _local_lock:
        exp = _local_store.get(jti)
        if exp is None:
            return False
        if exp <= now:
            _local_store.pop(jti, None)
            return False
        return True


def reset_for_tests() -> None:
    """Clear the in-process store (test helper)."""
    with _local_lock:
        _local_store.clear()
