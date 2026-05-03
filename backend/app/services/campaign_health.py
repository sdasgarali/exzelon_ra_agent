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
    """Calculate health score for a single campaign.

    Uses live queries against OutreachEvent instead of stale denormalized
    counters to ensure accuracy even when counters are out of sync.
    """
    campaign = db.query(Campaign).filter(
        Campaign.campaign_id == campaign_id
    ).first()
    if not campaign:
        return {"score": 0, "components": {}}

    # Live counts from OutreachEvent — not stale denormalized counters
    total_sent = db.query(OutreachEvent).filter(
        OutreachEvent.campaign_id == campaign_id,
        OutreachEvent.sent_at.isnot(None),
    ).count()

    total_contacts = db.query(CampaignContact).filter(
        CampaignContact.campaign_id == campaign_id,
    ).count()

    if total_sent < 5:
        return {"score": None, "components": {}, "reason": "insufficient_data"}

    total_bounced = db.query(OutreachEvent).filter(
        OutreachEvent.campaign_id == campaign_id,
        OutreachEvent.status == OutreachStatus.BOUNCED,
    ).count()

    total_opened = db.query(OutreachEvent).filter(
        OutreachEvent.campaign_id == campaign_id,
        OutreachEvent.opened_at.isnot(None),
    ).count()

    total_replied = db.query(OutreachEvent).filter(
        OutreachEvent.campaign_id == campaign_id,
        OutreachEvent.reply_detected_at.isnot(None),
    ).count()

    # Deliverability (0-100): low bounce rate = good
    bounce_rate = total_bounced / total_sent * 100 if total_sent > 0 else 0
    deliverability = max(0, 100 - bounce_rate * 10)  # 10% bounce = 0 score

    # Engagement (0-100): reply rate + open rate
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

    label = "Excellent" if score >= 80 else "Fair" if score >= 50 else "Poor"

    # Build explanation lines
    deliv_pts = round(deliverability * 0.4, 1)
    engage_pts = round(engagement * 0.35, 1)
    vol_pts = round(volume * 0.25, 1)

    explanation = [
        f"Deliverability: {round(deliverability)}/100 ({deliv_pts}/40 pts) — {round(bounce_rate, 1)}% bounce rate",
        f"Engagement: {round(engagement)}/100 ({engage_pts}/35 pts) — {round(reply_rate, 1)}% reply, {round(open_rate, 1)}% open",
        f"Volume: {round(volume)}/100 ({vol_pts}/25 pts) — {round(completion_rate, 1)}% completion",
    ]

    # Build recommendations based on weak components
    recommendations = []
    if deliverability < 70:
        recommendations.append("High bounce rate detected — verify email addresses before sending and check domain reputation.")
    if reply_rate < 1:
        recommendations.append("Very low reply rate — consider personalizing subject lines and email copy.")
    elif reply_rate < 3:
        recommendations.append("Reply rate is below average — try A/B testing different call-to-action approaches.")
    if open_rate < 15:
        recommendations.append("Low open rate — experiment with shorter subject lines and different send times.")
    elif open_rate < 30:
        recommendations.append("Open rate could improve — test subject line variations and sender name.")
    if volume < 50 and active_contacts == 0:
        recommendations.append("Campaign appears stalled — all contacts have been processed or removed.")
    if not recommendations:
        recommendations.append("Campaign is performing well — maintain current sending patterns.")

    return {
        "score": score,
        "label": label,
        "components": {
            "deliverability": round(deliverability, 1),
            "engagement": round(engagement, 1),
            "volume": round(volume, 1),
        },
        "metrics": {
            "total_sent": total_sent,
            "total_opened": total_opened,
            "total_replied": total_replied,
            "total_bounced": total_bounced,
            "bounce_rate": round(bounce_rate, 1),
            "reply_rate": round(reply_rate, 1),
            "open_rate": round(open_rate, 1),
            "completion_rate": round(completion_rate, 1),
        },
        "explanation": explanation,
        "recommendations": recommendations,
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
