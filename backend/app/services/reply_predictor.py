"""Statistical reply prediction based on historical engagement data."""
import structlog
from sqlalchemy.orm import Session
from sqlalchemy import func

logger = structlog.get_logger()


def predict_reply_likelihood(contact_id: int, db: Session) -> dict:
    """Predict reply likelihood for a contact using statistical features."""
    from app.db.models.outreach import OutreachEvent
    from app.db.models.contact import ContactDetails
    from app.db.models.lead import LeadDetails
    from app.db.models.lead_contact import LeadContactAssociation
    from app.db.models.campaign import CampaignContact

    contact = db.query(ContactDetails).filter(
        ContactDetails.contact_id == contact_id
    ).first()
    if not contact:
        return {"score": 0, "level": "unknown", "factors": {}}

    # Feature 1: Industry reply rate
    industry_rate = 0.0
    try:
        assoc = db.query(LeadContactAssociation).filter(
            LeadContactAssociation.contact_id == contact_id
        ).first()
        if assoc:
            lead = db.query(LeadDetails).filter(LeadDetails.lead_id == assoc.lead_id).first()
            if lead and lead.industry:
                # Get all contacts in same industry
                industry_leads = db.query(LeadDetails.lead_id).filter(
                    LeadDetails.industry == lead.industry
                ).subquery()
                industry_contacts = db.query(LeadContactAssociation.contact_id).filter(
                    LeadContactAssociation.lead_id.in_(db.query(industry_leads))
                ).subquery()
                total_in_industry = db.query(func.count()).select_from(industry_contacts).scalar() or 0
                if total_in_industry > 0:
                    replied_in_industry = db.query(func.count(CampaignContact.id)).filter(
                        CampaignContact.contact_id.in_(db.query(industry_contacts)),
                        CampaignContact.status == "replied",
                    ).scalar() or 0
                    industry_rate = replied_in_industry / total_in_industry
    except Exception:
        pass

    # Feature 2: Title reply rate
    title_rate = 0.0
    try:
        if contact.title:
            title_keyword = contact.title.split()[0].lower() if contact.title else ""
            if title_keyword:
                similar_contacts = db.query(ContactDetails.contact_id).filter(
                    ContactDetails.title.ilike(f"%{title_keyword}%")
                ).subquery()
                total_similar = db.query(func.count()).select_from(similar_contacts).scalar() or 0
                if total_similar > 0:
                    replied_similar = db.query(func.count(CampaignContact.id)).filter(
                        CampaignContact.contact_id.in_(db.query(similar_contacts)),
                        CampaignContact.status == "replied",
                    ).scalar() or 0
                    title_rate = replied_similar / total_similar
    except Exception:
        pass

    # Feature 3: Recency factor (days since last contact)
    recency_factor = 0.5
    try:
        last_event = db.query(OutreachEvent).filter(
            OutreachEvent.contact_id == contact_id
        ).order_by(OutreachEvent.sent_at.desc()).first()
        if last_event and last_event.sent_at:
            from datetime import datetime
            days_since = (datetime.utcnow() - last_event.sent_at).days
            recency_factor = max(0, 1.0 - (days_since / 90.0))
    except Exception:
        pass

    # Feature 4: Previous engagement
    engagement_factor = 0.0
    try:
        opens = db.query(func.count(OutreachEvent.event_id)).filter(
            OutreachEvent.contact_id == contact_id,
            OutreachEvent.opened_at.isnot(None),
        ).scalar() or 0
        clicks = db.query(func.count(OutreachEvent.event_id)).filter(
            OutreachEvent.contact_id == contact_id,
            OutreachEvent.clicked_at.isnot(None),
        ).scalar() or 0
        engagement_factor = min((opens * 0.3 + clicks * 0.7) / 5.0, 1.0)
    except Exception:
        pass

    # Feature 5: Sequence position
    position_factor = 0.5
    try:
        active_enrollment = db.query(CampaignContact).filter(
            CampaignContact.contact_id == contact_id,
            CampaignContact.status == "active",
        ).first()
        if active_enrollment:
            # Earlier steps have higher reply probability
            position_factor = max(0, 1.0 - (active_enrollment.current_step - 1) * 0.15)
    except Exception:
        pass

    # Weighted composite score
    weights = {
        "industry_rate": 0.15,
        "title_rate": 0.15,
        "recency_factor": 0.20,
        "engagement_factor": 0.30,
        "position_factor": 0.20,
    }
    factors = {
        "industry_rate": round(industry_rate, 3),
        "title_rate": round(title_rate, 3),
        "recency_factor": round(recency_factor, 3),
        "engagement_factor": round(engagement_factor, 3),
        "position_factor": round(position_factor, 3),
    }
    score = sum(factors[k] * weights[k] for k in weights)
    score = round(min(max(score * 100, 0), 100))

    level = "high" if score >= 60 else "medium" if score >= 30 else "low"

    return {"score": score, "level": level, "factors": factors}
