"""Dashboard and KPI endpoints."""
import time
from datetime import date, datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, and_

from app.api.deps import get_db, get_current_active_user, get_current_tenant_id
from app.db.models.user import User
from app.db.models.lead import LeadDetails, LeadStatus
from app.db.models.client import ClientInfo, ClientCategory
from app.db.models.contact import ContactDetails
from app.db.models.email_validation import EmailValidationResult, ValidationStatus
from app.db.models.outreach import OutreachEvent, OutreachStatus
from app.db.models.sender_mailbox import SenderMailbox, WarmupStatus
from app.db.models.email_template import EmailTemplate, TemplateStatus
from app.db.query_helpers import tenant_filter

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

# Simple in-memory cache for expensive KPI queries (60s TTL)
_kpi_cache: dict = {"data": None, "expires": 0, "key": ""}


@router.get("/kpis")
async def get_kpis(
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Get main KPIs for dashboard."""
    # Check cache (60s TTL, scoped by tenant)
    cache_key = f"{tenant_id}:{from_date}:{to_date}"
    now = time.time()
    if _kpi_cache["key"] == cache_key and _kpi_cache["expires"] > now and _kpi_cache["data"]:
        return _kpi_cache["data"]

    # Default to last 30 days
    if not to_date:
        to_date = date.today()
    if not from_date:
        from_date = to_date - timedelta(days=30)

    # Total companies identified
    lead_q = tenant_filter(db.query(LeadDetails), LeadDetails, tenant_id)
    total_companies = lead_q.filter(
        LeadDetails.posting_date >= from_date,
        LeadDetails.posting_date <= to_date
    ).with_entities(func.count(func.distinct(LeadDetails.client_name))).scalar() or 0

    # Total leads
    total_leads = lead_q.filter(
        LeadDetails.posting_date >= from_date,
        LeadDetails.posting_date <= to_date
    ).with_entities(func.count(LeadDetails.lead_id)).scalar() or 0

    # Total valid emails (EmailValidationResult doesn't have tenant_id — skip filtering for now)
    total_valid = db.query(EmailValidationResult).filter(
        EmailValidationResult.status == ValidationStatus.VALID,
        EmailValidationResult.validated_at >= datetime.combine(from_date, datetime.min.time()),
        EmailValidationResult.validated_at <= datetime.combine(to_date, datetime.max.time())
    ).with_entities(func.count(EmailValidationResult.validation_id)).scalar() or 0

    # Total contacts
    contact_q = tenant_filter(db.query(ContactDetails), ContactDetails, tenant_id)
    total_contacts = contact_q.with_entities(
        func.count(ContactDetails.contact_id)
    ).scalar() or 0

    # Outreach stats (OutreachEvent doesn't have tenant_id yet — Phase 3)
    outreach_query = db.query(OutreachEvent).filter(
        OutreachEvent.sent_at >= datetime.combine(from_date, datetime.min.time()),
        OutreachEvent.sent_at <= datetime.combine(to_date, datetime.max.time())
    )

    total_sent = outreach_query.filter(OutreachEvent.status == OutreachStatus.SENT).count()
    total_bounced = outreach_query.filter(OutreachEvent.status == OutreachStatus.BOUNCED).count()
    total_replied = outreach_query.filter(OutreachEvent.status == OutreachStatus.REPLIED).count()

    bounce_rate = (total_bounced / total_sent * 100) if total_sent > 0 else 0
    reply_rate = (total_replied / total_sent * 100) if total_sent > 0 else 0

    result = {
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

    _kpi_cache["data"] = result
    _kpi_cache["key"] = cache_key
    _kpi_cache["expires"] = now + 60  # 60 second TTL

    return result


@router.get("/leads-sourced")
async def get_leads_sourced(
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Tab 1 - Leads Sourced."""
    query = tenant_filter(db.query(LeadDetails), LeadDetails, tenant_id)

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
    current_user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Tab 2 - Contacts Identified."""
    contacts = tenant_filter(db.query(ContactDetails), ContactDetails, tenant_id).order_by(
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
    status: Optional[str] = None,
    channel: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Tab 3 - Outreach Sent."""
    # OutreachEvent doesn't have tenant_id yet (Phase 3) — no tenant filter for now
    query = db.query(OutreachEvent)

    if from_date:
        query = query.filter(OutreachEvent.sent_at >= datetime.combine(from_date, datetime.min.time()))
    if to_date:
        query = query.filter(OutreachEvent.sent_at <= datetime.combine(to_date, datetime.max.time()))
    if status:
        query = query.filter(OutreachEvent.status == status)
    if channel:
        query = query.filter(OutreachEvent.channel == channel)

    # For search, we need to join with contacts
    if search:
        query = query.join(ContactDetails, ContactDetails.contact_id == OutreachEvent.contact_id).filter(
            (ContactDetails.first_name.ilike(f"%{search}%")) |
            (ContactDetails.last_name.ilike(f"%{search}%")) |
            (ContactDetails.email.ilike(f"%{search}%")) |
            (ContactDetails.client_name.ilike(f"%{search}%")) |
            (OutreachEvent.subject.ilike(f"%{search}%"))
        )

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
    current_user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Tab 4 - Client Category Tracking."""
    client_q = tenant_filter(db.query(ClientInfo), ClientInfo, tenant_id)
    by_category = client_q.with_entities(
        ClientInfo.client_category,
        func.count(ClientInfo.client_id)
    ).group_by(ClientInfo.client_category).all()

    # Also get client list by category
    clients = tenant_filter(db.query(ClientInfo), ClientInfo, tenant_id).order_by(ClientInfo.client_name).all()

    return {
        "summary": {cat.value: count for cat, count in by_category if cat},
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
    current_user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Get trend data for charts."""
    end_date = date.today()
    start_date = end_date - timedelta(days=days)

    # Daily leads count
    daily_leads = tenant_filter(db.query(LeadDetails), LeadDetails, tenant_id).with_entities(
        func.date(LeadDetails.created_at).label('date'),
        func.count(LeadDetails.lead_id).label('count')
    ).filter(
        LeadDetails.created_at >= datetime.combine(start_date, datetime.min.time())
    ).group_by(func.date(LeadDetails.created_at)).all()

    # Daily outreach count
    daily_outreach = db.query(OutreachEvent).with_entities(
        func.date(OutreachEvent.sent_at).label('date'),
        func.count(OutreachEvent.event_id).label('count')
    ).filter(
        OutreachEvent.sent_at >= datetime.combine(start_date, datetime.min.time())
    ).group_by(func.date(OutreachEvent.sent_at)).all()

    return {
        "daily_leads": [{"date": str(d), "count": c} for d, c in daily_leads],
        "daily_outreach": [{"date": str(d), "count": c} for d, c in daily_outreach]
    }


@router.get("/stats")
async def get_dashboard_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Consolidated dashboard statistics (all-time, no date filter)."""
    # Leads (tenant-scoped)
    lead_q = tenant_filter(db.query(LeadDetails), LeadDetails, tenant_id)
    total_leads = lead_q.with_entities(
        func.count(LeadDetails.lead_id)
    ).scalar() or 0
    by_status = lead_q.with_entities(
        LeadDetails.lead_status, func.count(LeadDetails.lead_id)
    ).group_by(LeadDetails.lead_status).all()
    by_source = lead_q.with_entities(
        LeadDetails.source, func.count(LeadDetails.lead_id)
    ).group_by(LeadDetails.source).all()

    # Contacts (tenant-scoped)
    contact_q = tenant_filter(db.query(ContactDetails), ContactDetails, tenant_id)
    total_contacts = contact_q.with_entities(
        func.count(ContactDetails.contact_id)
    ).scalar() or 0
    by_validation = contact_q.with_entities(
        ContactDetails.validation_status, func.count(ContactDetails.contact_id)
    ).group_by(ContactDetails.validation_status).all()

    # Outreach (no tenant_id yet — Phase 3)
    total_sent = db.query(OutreachEvent).filter(
        OutreachEvent.status == OutreachStatus.SENT
    ).with_entities(func.count(OutreachEvent.event_id)).scalar() or 0
    total_replied = db.query(OutreachEvent).filter(
        OutreachEvent.status == OutreachStatus.REPLIED
    ).with_entities(func.count(OutreachEvent.event_id)).scalar() or 0
    total_bounced = db.query(OutreachEvent).filter(
        OutreachEvent.status == OutreachStatus.BOUNCED
    ).with_entities(func.count(OutreachEvent.event_id)).scalar() or 0
    total_skipped = db.query(OutreachEvent).filter(
        OutreachEvent.status == OutreachStatus.SKIPPED
    ).with_entities(func.count(OutreachEvent.event_id)).scalar() or 0
    reply_rate = (total_replied / total_sent * 100) if total_sent > 0 else 0
    bounce_rate = (total_bounced / total_sent * 100) if total_sent > 0 else 0

    # Mailboxes (tenant-scoped)
    mb_q = tenant_filter(db.query(SenderMailbox), SenderMailbox, tenant_id)
    total_mailboxes = mb_q.with_entities(
        func.count(SenderMailbox.mailbox_id)
    ).scalar() or 0
    active_mailboxes = mb_q.filter(
        SenderMailbox.is_active == True,
        SenderMailbox.warmup_status == WarmupStatus.ACTIVE
    ).with_entities(func.count(SenderMailbox.mailbox_id)).scalar() or 0
    ready_to_send = tenant_filter(db.query(SenderMailbox), SenderMailbox, tenant_id).filter(
        SenderMailbox.is_active == True,
        SenderMailbox.warmup_status.in_([WarmupStatus.ACTIVE, WarmupStatus.COLD_READY])
    ).with_entities(func.count(SenderMailbox.mailbox_id)).scalar() or 0
    warming_up_mailboxes = tenant_filter(db.query(SenderMailbox), SenderMailbox, tenant_id).filter(
        SenderMailbox.warmup_status == WarmupStatus.WARMING_UP
    ).with_entities(func.count(SenderMailbox.mailbox_id)).scalar() or 0
    by_warmup_status = tenant_filter(db.query(SenderMailbox), SenderMailbox, tenant_id).with_entities(
        SenderMailbox.warmup_status, func.count(SenderMailbox.mailbox_id)
    ).group_by(SenderMailbox.warmup_status).all()

    # Templates (no tenant_id yet — Phase 3)
    total_templates = db.query(EmailTemplate).with_entities(
        func.count(EmailTemplate.template_id)
    ).scalar() or 0
    active_templates = db.query(EmailTemplate).filter(
        EmailTemplate.status == TemplateStatus.ACTIVE
    ).with_entities(func.count(EmailTemplate.template_id)).scalar() or 0

    return {
        "leads": {
            "total": total_leads,
            "by_status": {s.value: c for s, c in by_status if s},
            "by_source": {s: c for s, c in by_source if s}
        },
        "contacts": {
            "total": total_contacts,
            "by_validation_status": {str(v): c for v, c in by_validation if v}
        },
        "outreach": {
            "total_sent": total_sent,
            "total_replied": total_replied,
            "total_bounced": total_bounced,
            "total_skipped": total_skipped,
            "reply_rate": round(reply_rate, 2),
            "bounce_rate": round(bounce_rate, 2)
        },
        "mailboxes": {
            "total": total_mailboxes,
            "active": active_mailboxes,
            "ready_to_send": ready_to_send,
            "warming_up": warming_up_mailboxes,
            "by_warmup_status": {s.value if s else "unknown": c for s, c in by_warmup_status}
        },
        "templates": {
            "total": total_templates,
            "active_count": active_templates
        }
    }
