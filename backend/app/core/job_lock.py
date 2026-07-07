"""MySQL advisory lock helper for scheduler job deduplication.

Prevents the same scheduler job from running simultaneously across
multiple Uvicorn workers. Uses MySQL GET_LOCK/RELEASE_LOCK which
are session-scoped and automatically released on disconnect.
"""
import structlog
from contextlib import contextmanager

logger = structlog.get_logger()


@contextmanager
def advisory_lock(lock_name: str, timeout: int = 0):
    """Acquire a MySQL advisory lock. Yields True if acquired, False if not.

    Usage:
        with advisory_lock("campaign_processor") as acquired:
            if not acquired:
                return  # another worker is running this job
            do_work()

    Args:
        lock_name: Unique lock identifier (prefixed with 'exz_' automatically)
        timeout: Seconds to wait for lock (0 = non-blocking)
    """
    from app.db.base import SessionLocal
    from app.core.config import settings

    full_name = f"exz_{lock_name}"

    # SQLite doesn't support advisory locks — always grant
    if settings.DB_TYPE != "mysql":
        yield True
        return

    db = SessionLocal()
    acquired = False
    try:
        from sqlalchemy import text
        result = db.execute(text("SELECT GET_LOCK(:name, :timeout)"), {
            "name": full_name, "timeout": timeout,
        })
        acquired = result.scalar() == 1

        if not acquired:
            logger.info("advisory_lock_skip", lock=full_name, reason="held_by_another_worker")

        yield acquired
    except Exception as e:
        logger.warning("advisory_lock_error", lock=full_name, error=str(e))
        # On error, yield True so the job still runs (fail-open)
        yield True
    finally:
        if acquired:
            try:
                from sqlalchemy import text
                db.execute(text("SELECT RELEASE_LOCK(:name)"), {"name": full_name})
            except Exception:
                pass  # Lock auto-releases on session close anyway
        db.close()
