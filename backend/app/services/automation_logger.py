"""Automation event logger — records what the system does for user transparency."""
import json
import structlog
from typing import Any, Optional
from sqlalchemy.orm import Session

from app.db.models.automation_event import AutomationEvent

logger = structlog.get_logger()


def log_automation_event(
    db: Session,
    event_type: str,
    title: str,
    details: Optional[Any] = None,
    source: str = "scheduler",
    status: str = "success",
) -> None:
    """Log an automation event to the database.

    Args:
        db: Database session.
        event_type: Category — scheduler_run, ai_classify, ai_suggest,
                    campaign_send, reply_detected, inbox_sync, lead_sourcing, etc.
        title: Human-readable summary, e.g. "Campaign processor ran — 3 emails sent".
        details: Arbitrary dict/list serialized as JSON.
        source: Who triggered it — scheduler, user, api.
        status: success, error, or skipped.
    """
    try:
        event = AutomationEvent(
            event_type=event_type,
            source=source,
            title=title,
            details_json=json.dumps(details) if details else None,
            status=status,
        )
        db.add(event)
        db.commit()
    except Exception as e:
        logger.warning("Failed to log automation event", error=str(e))
        try:
            db.rollback()
        except Exception:
            pass
