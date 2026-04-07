"""Agent Context Builder — aggregates all data about a lead/contact for AI consumption.

Builds a unified context dict from: contact details, lead/job data, company info,
outreach history, engagement signals, and scoring. This context is passed to every
AI module so decisions are informed by the full picture.
"""
from datetime import datetime
from typing import Any, Dict, Optional

import structlog
from sqlalchemy.orm import Session

logger = structlog.get_logger()


def build_contact_context(
    contact,
    lead=None,
    history: Optional[Dict[str, Any]] = None,
    campaign=None,
) -> Dict[str, Any]:
    """Build a unified context dict for AI modules.

    Args:
        contact: ContactDetails model instance
        lead: Optional LeadDetails model instance
        history: Optional pre-built interaction history dict
        campaign: Optional Campaign model instance

    Returns:
        Dict with keys: contact, lead, company, campaign, history, scores
    """
    return {
        "contact": _extract_contact(contact),
        "lead": _extract_lead(lead),
        "company": _extract_company(contact, lead),
        "campaign": _extract_campaign(campaign),
        "history": history or _empty_history(),
        "scores": _extract_scores(contact, lead),
        "built_at": datetime.utcnow().isoformat(),
    }


def build_interaction_history(
    db: Session,
    contact_id: int,
    tenant_id: int,
) -> Dict[str, Any]:
    """Query DB for contact's outreach history.

    Returns a dict with: emails_sent, emails_replied, last_reply_intent,
    last_outreach_date, objections, opens, clicks.
    """
    try:
        from app.db.models.outreach import OutreachEvent, OutreachStatus
        from app.db.models.inbox_message import InboxMessage, MessageDirection

        sent_count = db.query(OutreachEvent).filter(
            OutreachEvent.contact_id == contact_id,
            OutreachEvent.tenant_id == tenant_id,
            OutreachEvent.status == OutreachStatus.SENT,
        ).count()

        replied_count = db.query(InboxMessage).filter(
            InboxMessage.contact_id == contact_id,
            InboxMessage.tenant_id == tenant_id,
            InboxMessage.direction == MessageDirection.RECEIVED,
        ).count()

        last_reply = db.query(InboxMessage).filter(
            InboxMessage.contact_id == contact_id,
            InboxMessage.tenant_id == tenant_id,
            InboxMessage.direction == MessageDirection.RECEIVED,
        ).order_by(InboxMessage.received_at.desc()).first()

        last_sent = db.query(OutreachEvent).filter(
            OutreachEvent.contact_id == contact_id,
            OutreachEvent.tenant_id == tenant_id,
            OutreachEvent.status == OutreachStatus.SENT,
        ).order_by(OutreachEvent.sent_at.desc()).first()

        open_count = db.query(OutreachEvent).filter(
            OutreachEvent.contact_id == contact_id,
            OutreachEvent.tenant_id == tenant_id,
            OutreachEvent.status == OutreachStatus.OPENED,
        ).count()

        click_count = db.query(OutreachEvent).filter(
            OutreachEvent.contact_id == contact_id,
            OutreachEvent.tenant_id == tenant_id,
            OutreachEvent.status == OutreachStatus.CLICKED,
        ).count()

        return {
            "emails_sent": sent_count,
            "emails_replied": replied_count,
            "emails_opened": open_count,
            "emails_clicked": click_count,
            "last_reply_intent": last_reply.category if last_reply else None,
            "last_reply_date": last_reply.received_at.isoformat() if last_reply and last_reply.received_at else None,
            "last_outreach_date": last_sent.sent_at.isoformat() if last_sent and last_sent.sent_at else None,
            "objections": [],
        }
    except Exception as e:
        logger.warning("build_interaction_history_failed", error=str(e), contact_id=contact_id)
        return _empty_history()


def _extract_contact(contact) -> Dict[str, Any]:
    if not contact:
        return {"name": None, "email": None, "title": None, "priority": None}
    return {
        "id": getattr(contact, "contact_id", None),
        "name": f"{contact.first_name or ''} {contact.last_name or ''}".strip() or None,
        "first_name": getattr(contact, "first_name", None),
        "email": getattr(contact, "email", None),
        "title": getattr(contact, "title", None),
        "phone": getattr(contact, "phone", None),
        "priority": getattr(contact, "priority_level", None),
        "validation_status": getattr(contact, "validation_status", None),
        "outreach_status": getattr(contact, "outreach_status", None),
    }


def _extract_lead(lead) -> Dict[str, Any]:
    if not lead:
        return {"job_title": None, "state": None, "city": None, "industry": None}
    return {
        "id": getattr(lead, "lead_id", None),
        "job_title": getattr(lead, "job_title", None),
        "state": getattr(lead, "state", None),
        "city": getattr(lead, "city", None),
        "industry": getattr(lead, "industry", None),
        "company_size": getattr(lead, "company_size", None),
        "salary_min": getattr(lead, "salary_min", None),
        "salary_max": getattr(lead, "salary_max", None),
        "posting_date": lead.posting_date.isoformat() if getattr(lead, "posting_date", None) else None,
        "employer_linkedin": getattr(lead, "employer_linkedin_url", None),
        "employer_website": getattr(lead, "employer_website", None),
    }


def _extract_company(contact, lead) -> Dict[str, Any]:
    return {
        "name": getattr(contact, "client_name", None) if contact else None,
        "industry": getattr(lead, "industry", None) if lead else None,
        "size": getattr(lead, "company_size", None) if lead else None,
        "linkedin": getattr(lead, "employer_linkedin_url", None) if lead else None,
        "website": getattr(lead, "employer_website", None) if lead else None,
    }


def _extract_campaign(campaign) -> Dict[str, Any]:
    if not campaign:
        return {"id": None, "name": None}
    return {
        "id": getattr(campaign, "campaign_id", None),
        "name": getattr(campaign, "name", None),
        "auto_reply_enabled": getattr(campaign, "auto_reply_enabled", False),
        "preview_mode": getattr(campaign, "preview_mode", False),
    }


def _extract_scores(contact, lead) -> Dict[str, Any]:
    return {
        "lead_score": getattr(contact, "lead_score", None) if contact else None,
        "priority": getattr(contact, "priority_level", None) if contact else None,
    }


def _empty_history() -> Dict[str, Any]:
    return {
        "emails_sent": 0,
        "emails_replied": 0,
        "emails_opened": 0,
        "emails_clicked": 0,
        "last_reply_intent": None,
        "last_reply_date": None,
        "last_outreach_date": None,
        "objections": [],
    }
