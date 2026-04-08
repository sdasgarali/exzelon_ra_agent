"""Auto-pause campaigns that exceed bounce/spam thresholds."""
import structlog
from sqlalchemy.orm import Session

from app.db.models.campaign import Campaign, CampaignStatus

logger = structlog.get_logger()


def check_campaign_health(db: Session, tenant_id=None):
    """Check all active campaigns and auto-pause unhealthy ones.

    Called by scheduler every hour.
    """
    from app.db.query_helpers import tenant_filter

    campaigns_q = db.query(Campaign).filter(
        Campaign.status == CampaignStatus.ACTIVE,
        Campaign.is_archived == False,
    )
    if tenant_id:
        campaigns_q = tenant_filter(campaigns_q, Campaign, tenant_id)

    campaigns = campaigns_q.all()
    paused_count = 0

    for campaign in campaigns:
        total_sent = campaign.total_sent or 0
        if total_sent < 10:  # Need minimum data
            continue

        total_bounced = campaign.total_bounced or 0
        bounce_rate = (total_bounced / total_sent * 100) if total_sent > 0 else 0

        # Check bounce threshold
        bounce_threshold = campaign.bounce_threshold if campaign.bounce_threshold is not None else 10
        if bounce_rate >= bounce_threshold:
            campaign.status = CampaignStatus.PAUSED
            campaign.auto_pause_reason = (
                f"Bounce rate {bounce_rate:.1f}% exceeded threshold {bounce_threshold}%"
            )
            paused_count += 1
            logger.warning(
                "campaign_auto_paused",
                campaign_id=campaign.campaign_id,
                reason="bounce_rate",
                rate=bounce_rate,
            )
            _create_pause_notification(db, campaign, campaign.auto_pause_reason)
            continue

        # Check spam/complaint threshold
        spam_threshold = campaign.spam_threshold if campaign.spam_threshold is not None else 5
        complaint_count = _get_campaign_complaint_count(db, campaign.campaign_id)
        spam_rate = (complaint_count / total_sent * 100) if total_sent > 0 else 0
        if spam_rate >= spam_threshold:
            campaign.status = CampaignStatus.PAUSED
            campaign.auto_pause_reason = (
                f"Spam/complaint rate {spam_rate:.1f}% exceeded threshold {spam_threshold}%"
            )
            paused_count += 1
            logger.warning(
                "campaign_auto_paused",
                campaign_id=campaign.campaign_id,
                reason="spam_rate",
                rate=spam_rate,
            )
            _create_pause_notification(db, campaign, campaign.auto_pause_reason)
            continue

    db.commit()
    return {"checked": len(campaigns), "paused": paused_count}


def _get_campaign_complaint_count(db: Session, campaign_id: int) -> int:
    """Count spam complaints for a campaign from automation_events."""
    try:
        from app.db.models.automation_event import AutomationEvent
        return db.query(AutomationEvent).filter(
            AutomationEvent.event_type == "spam_complaint",
            AutomationEvent.details.like(f'%"campaign_id": {campaign_id}%'),
        ).count()
    except Exception:
        # Fallback: check ESP feedback mailbox complaints proportionally
        try:
            from app.db.models.sender_mailbox import SenderMailbox
            from app.db.models.outreach import OutreachEvent, OutreachStatus
            # Get mailboxes used by this campaign
            mailbox_ids = db.query(OutreachEvent.sender_mailbox_id).filter(
                OutreachEvent.campaign_id == campaign_id,
                OutreachEvent.status == OutreachStatus.SENT,
            ).distinct().all()
            mailbox_ids = [m[0] for m in mailbox_ids if m[0]]
            if not mailbox_ids:
                return 0
            total_complaints = sum(
                (db.query(SenderMailbox).filter(
                    SenderMailbox.mailbox_id == mid
                ).first().complaint_count or 0)
                for mid in mailbox_ids
            )
            return total_complaints
        except Exception:
            return 0


def _create_pause_notification(db, campaign, reason):
    """Create a notification for auto-paused campaign."""
    try:
        from app.db.models.notification import NotificationEntry

        notif = NotificationEntry(
            tenant_id=campaign.tenant_id,
            title=f"Campaign '{campaign.name}' auto-paused",
            message=reason,
            category="campaign",
            priority="high",
            link="/dashboard/campaigns",
        )
        db.add(notif)
    except Exception:
        pass  # Notification is non-critical
