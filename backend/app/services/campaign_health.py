"""Campaign health score calculator.

Health = (deliverability * 0.4) + (engagement * 0.35) + (volume * 0.25)
Score range: 0-100. Recalculated daily by scheduler.
"""
import structlog
from sqlalchemy.orm import Session

from app.db.models.campaign import Campaign, CampaignStatus, CampaignContact, CampaignContactStatus
from app.db.models.outreach import OutreachEvent, OutreachStatus

logger = structlog.get_logger()


def calculate_campaign_health(campaign_id: int, db: Session) -> dict:
    """Calculate health score for a single campaign."""
    campaign = db.query(Campaign).filter(
        Campaign.campaign_id == campaign_id
    ).first()
    if not campaign:
        return {"score": 0, "components": {}}

    total_sent = campaign.total_sent or 0
    total_contacts = campaign.total_contacts or 0

    if total_sent < 5:
        return {"score": None, "components": {}, "reason": "insufficient_data"}

    # Deliverability (0-100): low bounce rate + low spam = good
    total_bounced = campaign.total_bounced or 0
    bounce_rate = total_bounced / total_sent * 100 if total_sent > 0 else 0
    deliverability = max(0, 100 - bounce_rate * 10)  # 10% bounce = 0 score

    # Engagement (0-100): reply rate + open rate
    total_replied = campaign.total_replied or 0
    total_opened = campaign.total_opened or 0
    reply_rate = total_replied / total_sent * 100 if total_sent > 0 else 0
    open_rate = total_opened / total_sent * 100 if total_sent > 0 else 0

    # Reply rate: 5%+ = 100, 0% = 0
    reply_score = min(100, reply_rate * 20)
    # Open rate: 40%+ = 100, 0% = 0
    open_score = min(100, open_rate * 2.5)
    engagement = reply_score * 0.6 + open_score * 0.4

    # Volume health (0-100): steady sending pace, not stalled
    active_contacts = db.query(CampaignContact).filter(
        CampaignContact.campaign_id == campaign_id,
        CampaignContact.status == CampaignContactStatus.ACTIVE,
    ).count()
    completion_rate = (total_contacts - active_contacts) / total_contacts * 100 if total_contacts > 0 else 0
    # Active campaign with contacts progressing = healthy
    volume = min(100, completion_rate + (50 if active_contacts > 0 else 0))

    # Weighted score
    score = round(deliverability * 0.4 + engagement * 0.35 + volume * 0.25)
    score = max(0, min(100, score))

    return {
        "score": score,
        "components": {
            "deliverability": round(deliverability, 1),
            "engagement": round(engagement, 1),
            "volume": round(volume, 1),
        },
        "metrics": {
            "bounce_rate": round(bounce_rate, 1),
            "reply_rate": round(reply_rate, 1),
            "open_rate": round(open_rate, 1),
            "completion_rate": round(completion_rate, 1),
        },
    }


def recalculate_all_health_scores(db: Session) -> dict:
    """Recalculate health scores for all active campaigns."""
    campaigns = db.query(Campaign).filter(
        Campaign.status.in_([CampaignStatus.ACTIVE, CampaignStatus.PAUSED]),
    ).all()

    updated = 0
    for campaign in campaigns:
        result = calculate_campaign_health(campaign.campaign_id, db)
        if result.get("score") is not None:
            campaign.health_score = result["score"]
            updated += 1

    db.commit()
    return {"campaigns_checked": len(campaigns), "scores_updated": updated}
