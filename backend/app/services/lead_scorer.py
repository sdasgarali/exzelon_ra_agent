"""Lead scoring engine — calculates 0-100 scores for contacts."""
import json
from datetime import datetime, timedelta
from typing import Dict, Any
import structlog
from sqlalchemy.orm import Session

from app.db.models.contact import ContactDetails
from app.db.models.outreach import OutreachEvent, OutreachStatus
from app.db.models.email_validation import EmailValidationResult, ValidationStatus

logger = structlog.get_logger()


def calculate_contact_score(contact: ContactDetails, db: Session) -> Dict[str, Any]:
    """Calculate lead score (0-100) for a single contact.

    Scoring breakdown:
    - Email engagement: 40 pts (opens 10, clicks 15, replies 15)
    - Contact quality: 25 pts (validation 10, priority 10, has phone 5)
    - Company fit: 20 pts (industry 10, size 10) — simplified
    - Recency: 15 pts (how recently sourced/updated)
    """
    factors = {}
    score = 0

    # 1. Email engagement (40 pts max)
    engagement_score = 0

    replied_count = db.query(OutreachEvent).filter(
        OutreachEvent.contact_id == contact.contact_id,
        OutreachEvent.reply_detected_at.isnot(None),
    ).count()
    if replied_count > 0:
        engagement_score += 15
        factors["replies"] = min(replied_count, 3)

    sent_count = db.query(OutreachEvent).filter(
        OutreachEvent.contact_id == contact.contact_id,
        OutreachEvent.status == OutreachStatus.SENT,
    ).count()
    if sent_count > 0 and replied_count > 0:
        engagement_score += 10  # opens proxy (if they replied, they opened)
        factors["opens"] = True

    # Clicks would require tracking data — simplified
    if replied_count >= 2:
        engagement_score += 15  # high engagement
        factors["high_engagement"] = True
    elif replied_count == 1:
        engagement_score += 5
        factors["some_engagement"] = True

    score += min(engagement_score, 40)
    factors["engagement_score"] = min(engagement_score, 40)

    # 2. Contact quality (25 pts max)
    quality_score = 0

    # Validation status
    if contact.validation_status in ["valid", "Valid"]:
        quality_score += 10
        factors["valid_email"] = True
    elif contact.validation_status in ["catch-all", "Catch-all"]:
        quality_score += 5
        factors["catchall_email"] = True

    # Priority level
    if contact.priority_level:
        priority_map = {
            "p1_job_poster": 10,
            "p2_hr_ta_recruiter": 8,
            "p3_hr_manager": 6,
            "p4_ops_leader": 4,
            "p5_functional_manager": 2,
        }
        p_val = contact.priority_level
        if hasattr(p_val, "value"):
            p_val = p_val.value
        quality_score += priority_map.get(p_val, 2)
        factors["priority"] = p_val

    # Has phone
    if contact.phone:
        quality_score += 5
        factors["has_phone"] = True

    score += min(quality_score, 25)
    factors["quality_score"] = min(quality_score, 25)

    # 3. Company fit (20 pts max) — simplified
    fit_score = 10  # base score for having company name
    if contact.client_name:
        factors["has_company"] = True
    if contact.title:
        fit_score += 5
        factors["has_title"] = True
    if contact.location_state:
        fit_score += 5
        factors["has_location"] = True

    score += min(fit_score, 20)
    factors["fit_score"] = min(fit_score, 20)

    # 4. Recency (15 pts max)
    recency_score = 0
    if contact.created_at:
        days_old = (datetime.utcnow() - contact.created_at).days
        if days_old <= 7:
            recency_score = 15
        elif days_old <= 30:
            recency_score = 12
        elif days_old <= 90:
            recency_score = 8
        elif days_old <= 180:
            recency_score = 4
        else:
            recency_score = 1
        factors["days_old"] = days_old

    score += recency_score
    factors["recency_score"] = recency_score

    return {"score": min(score, 100), "factors": factors}


def recalculate_all_scores(db: Session) -> Dict[str, Any]:
    """Recalculate lead scores for all active contacts."""
    contacts = db.query(ContactDetails).filter(
        ContactDetails.is_archived == False,
    ).all()

    updated = 0
    for contact in contacts:
        result = calculate_contact_score(contact, db)
        contact.lead_score = result["score"]
        contact.lead_score_factors_json = json.dumps(result["factors"])
        contact.lead_score_updated_at = datetime.utcnow()
        updated += 1

    db.commit()

    # Update deal probabilities from new scores
    try:
        from app.services.deal_automation import update_deal_probability_from_score
        prob_updated = 0
        for contact in contacts:
            prob_updated += update_deal_probability_from_score(contact.contact_id, db)
        if prob_updated:
            db.commit()
            logger.info("Deal probabilities updated from lead scores", updated=prob_updated)
    except Exception as e:
        logger.warning("Deal probability update failed", error=str(e))

    logger.info("Lead scoring complete", updated=updated)
    return {"updated": updated}
