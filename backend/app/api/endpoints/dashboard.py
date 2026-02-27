"""Dashboard and KPI endpoints."""
from datetime import date, datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, and_

from app.api.deps import get_db, get_current_active_user
from app.db.models.user import User
from app.db.models.lead import LeadDetails, LeadStatus
from app.db.models.client import ClientInfo, ClientCategory
from app.db.models.contact import ContactDetails
from app.db.models.email_validation import EmailValidationResult, ValidationStatus
from app.db.models.outreach import OutreachEvent, OutreachStatus

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/kpis")
async def get_kpis(
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get main KPIs for dashboard."""
    # Default to last 30 days
    if not to_date:
        to_date = date.today()
    if not from_date:
        from_date = to_date - timedelta(days=30)

    # Total companies identified
    total_companies = db.query(func.count(func.distinct(LeadDetails.client_name))).filter(
        LeadDetails.posting_date >= from_date,
        LeadDetails.posting_date <= to_date
    ).scalar() or 0

    # Total leads
    total_leads = db.query(func.count(LeadDetails.lead_id)).filter(
        LeadDetails.posting_date >= from_date,
        LeadDetails.posting_date <= to_date
    ).scalar() or 0

    # Total valid emails
    total_valid = db.query(func.count(EmailValidationResult.validation_id)).filter(
        EmailValidationResult.status == ValidationStatus.VALID,
        EmailValidationResult.validated_at >= datetime.combine(from_date, datetime.min.time()),
        EmailValidationResult.validated_at <= datetime.combine(to_date, datetime.max.time())
    ).scalar() or 0

    # Total contacts
    total_contacts = db.query(func.count(ContactDetails.contact_id)).scalar() or 0

    # Outreach stats
    outreach_query = db.query(OutreachEvent).filter(
        OutreachEvent.sent_at >= datetime.combine(from_date, datetime.min.time()),
        OutreachEvent.sent_at <= datetime.combine(to_date, datetime.max.time())
    )

    total_sent = outreach_query.filter(OutreachEvent.status == OutreachStatus.SENT).count()
    total_bounced = outreach_query.filter(OutreachEvent.status == OutreachStatus.BOUNCED).count()
    total_replied = outreach_query.filter(OutreachEvent.status == OutreachStatus.REPLIED).count()

    bounce_rate = (total_bounced / total_sent * 100) if total_sent > 0 else 0
    reply_rate = (total_replied / total_sent * 100) if total_sent > 0 else 0

    return {
        "period": {"from": from_date.isoformat(), "to": to_date.isoformat()},
        "total_companies_identified": total_companies,
        "total_leads": total_leads,
        "total_contacts": total_contacts,
        "total_valid_emails": total_valid,
        "emails_sent": total_sent,
        "emails_bounced": total_bounced,
        "emails_replied": total_replied,
        "bounce_rate_percent": round(bounce_rate, 2),
        "reply_rate_percent": round(reply_rate, 2)
    }


@router.get("/leads-sourced")
async def get_leads_sourced(
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Tab 1 - Leads Sourced."""
    query = db.query(LeadDetails)

    if from_date:
        query = query.filter(LeadDetails.posting_date >= from_date)
    if to_date:
        query = query.filter(LeadDetails.posting_date <= to_date)

    leads = query.order_by(LeadDetails.created_at.desc()).limit(limit).all()

    return [
        {
            "date_sourced": lead.created_at.date().isoformat() if lead.created_at else None,
            "company": lead.client_name,
            "job_title": lead.job_title,
            "state": lead.state,
            "salary_range": f"${lead.salary_min or 0:,.0f} - ${lead.salary_max or 0:,.0f}",
            "source": lead.source,
            "ra_name": lead.ra_name
        }
        for lead in leads
    ]


@router.get("/contacts-identified")
async def get_contacts_identified(
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Tab 2 - Contacts Identified."""
    contacts = db.query(ContactDetails).order_by(
        ContactDetails.created_at.desc()
    ).limit(limit).all()

    return [
        {
            "contact_name": f"{c.first_name} {c.last_name}",
            "title": c.title,
            "email": c.email,
            "state": c.location_state,
            "validation_status": c.validation_status,
            "priority_level": c.priority_level.value if c.priority_level else None
        }
        for c in contacts
    ]


@router.get("/outreach-sent")
async def get_outreach_sent(
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Tab 3 - Outreach Sent."""
    query = db.query(OutreachEvent)

    if from_date:
        query = query.filter(OutreachEvent.sent_at >= datetime.combine(from_date, datetime.min.time()))
    if to_date:
        query = query.filter(OutreachEvent.sent_at <= datetime.combine(to_date, datetime.max.time()))

    events = query.order_by(OutreachEvent.sent_at.desc()).limit(limit).all()

    results = []
    for e in events:
        # Join with contact for name/email
        contact = db.query(ContactDetails).filter(
            ContactDetails.contact_id == e.contact_id
        ).first() if e.contact_id else None

        results.append({
            "event_id": e.event_id,
            "date_sent": e.sent_at.isoformat() if e.sent_at else None,
            "contact_name": f"{contact.first_name} {contact.last_name}" if contact else None,
            "client_name": contact.client_name if contact else None,
            "email": contact.email if contact else None,
            "template_id": e.template_id,
            "subject": e.subject,
            "status": e.status.value if e.status else None,
            "channel": e.channel.value if e.channel else None,
            "bounce_reason": e.bounce_reason,
            "body_html": e.body_html,
            "reply_body": e.reply_body,
            "reply_subject": e.reply_subject,
            "reply_detected_at": e.reply_detected_at.isoformat() if e.reply_detected_at else None,
            "sender_mailbox_id": e.sender_mailbox_id,
        })
    return results


@router.get("/client-categories")
async def get_client_categories(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Tab 4 - Client Category Tracking."""
    by_category = db.query(
        ClientInfo.client_category,
        func.count(ClientInfo.client_id)
    ).group_by(ClientInfo.client_category).all()

    # Also get client list by category
    clients = db.query(ClientInfo).order_by(ClientInfo.client_name).all()

    return {
        "summary": {str(cat): count for cat, count in by_category if cat},
        "clients": [
            {
                "client_name": c.client_name,
                "category": c.client_category.value if c.client_category else None,
                "status": c.status.value if c.status else None,
                "service_count": c.service_count
            }
            for c in clients
        ]
    }


@router.get("/trends")
async def get_trends(
    days: int = Query(30, ge=7, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get trend data for charts."""
    end_date = date.today()
    start_date = end_date - timedelta(days=days)

    # Daily leads count
    daily_leads = db.query(
        func.date(LeadDetails.created_at).label('date'),
        func.count(LeadDetails.lead_id).label('count')
    ).filter(
        LeadDetails.created_at >= datetime.combine(start_date, datetime.min.time())
    ).group_by(func.date(LeadDetails.created_at)).all()

    # Daily outreach count
    daily_outreach = db.query(
        func.date(OutreachEvent.sent_at).label('date'),
        func.count(OutreachEvent.event_id).label('count')
    ).filter(
        OutreachEvent.sent_at >= datetime.combine(start_date, datetime.min.time())
    ).group_by(func.date(OutreachEvent.sent_at)).all()

    return {
        "daily_leads": [{"date": str(d), "count": c} for d, c in daily_leads],
        "daily_outreach": [{"date": str(d), "count": c} for d, c in daily_outreach]
    }
