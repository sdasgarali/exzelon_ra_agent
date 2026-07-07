"""Learning Engine — tracks outcomes to surface what works.

Records: which emails got replies, which intents were correctly classified,
which campaigns have best engagement. Surfaces aggregate stats per tenant
for strategy optimization.
"""
from typing import Any, Dict, Optional

import structlog
from sqlalchemy.orm import Session

logger = structlog.get_logger()


def record_send_outcome(
    db: Session,
    tenant_id: int,
    contact_id: int,
    campaign_id: int,
    outcome: str,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    """Record the outcome of a sent email for learning.

    Outcomes: sent, opened, clicked, replied, bounced, unsubscribed
    """
    try:
        from app.services.automation_logger import log_automation_event

        log_automation_event(
            db,
            event_type=f"ai_learning_{outcome}",
            title=f"Send outcome: {outcome} for contact {contact_id}",
            details={
                "contact_id": contact_id,
                "campaign_id": campaign_id,
                "outcome": outcome,
                "tenant_id": tenant_id,
                **(details or {}),
            },
            status="success",
            source="learning_engine",
        )
    except Exception as e:
        logger.warning("learning_record_failed", error=str(e))


def get_campaign_performance(
    db: Session,
    campaign_id: int,
    tenant_id: int,
) -> Dict[str, Any]:
    """Get aggregate performance stats for a campaign."""
    try:
        from app.db.models.outreach import OutreachEvent, OutreachStatus

        total_sent = db.query(OutreachEvent).filter(
            OutreachEvent.campaign_id == campaign_id,
            OutreachEvent.tenant_id == tenant_id,
            OutreachEvent.status == OutreachStatus.SENT,
        ).count()

        total_opened = db.query(OutreachEvent).filter(
            OutreachEvent.campaign_id == campaign_id,
            OutreachEvent.tenant_id == tenant_id,
            OutreachEvent.status == OutreachStatus.OPENED,
        ).count()

        total_replied = db.query(OutreachEvent).filter(
            OutreachEvent.campaign_id == campaign_id,
            OutreachEvent.tenant_id == tenant_id,
            OutreachEvent.status == OutreachStatus.REPLIED,
        ).count()

        total_bounced = db.query(OutreachEvent).filter(
            OutreachEvent.campaign_id == campaign_id,
            OutreachEvent.tenant_id == tenant_id,
            OutreachEvent.status == OutreachStatus.BOUNCED,
        ).count()

        open_rate = (total_opened / total_sent * 100) if total_sent > 0 else 0
        reply_rate = (total_replied / total_sent * 100) if total_sent > 0 else 0
        bounce_rate = (total_bounced / total_sent * 100) if total_sent > 0 else 0

        return {
            "campaign_id": campaign_id,
            "total_sent": total_sent,
            "total_opened": total_opened,
            "total_replied": total_replied,
            "total_bounced": total_bounced,
            "open_rate": round(open_rate, 1),
            "reply_rate": round(reply_rate, 1),
            "bounce_rate": round(bounce_rate, 1),
        }
    except Exception as e:
        logger.warning("campaign_performance_query_failed", error=str(e))
        return {"campaign_id": campaign_id, "total_sent": 0}
