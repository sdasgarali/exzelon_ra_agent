"""Reports endpoints — client analytics, campaign performance, mailbox health,
daily activity, contact engagement, domain deliverability."""
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, case
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.api.deps.auth import require_role, get_current_tenant_id
from app.db.query_helpers import tenant_filter
from app.db.models.user import User, UserRole
from app.db.models.client import ClientInfo
from app.db.models.contact import ContactDetails
from app.db.models.lead import LeadDetails
from app.db.models.outreach import OutreachEvent, OutreachStatus
from app.db.models.campaign import Campaign, CampaignContact, CampaignContactStatus
from app.db.models.deal import Deal
from app.db.models.sender_mailbox import SenderMailbox
from app.core.config import settings

router = APIRouter(prefix="/reports", tags=["Reports"])

EXPORT_CAP = 10_000


# ---------------------------------------------------------------------------
# Tab 1: Client Analytics
# ---------------------------------------------------------------------------

@router.get("/client-analytics")
def client_analytics(
    search: Optional[str] = Query(None),
    industry: Optional[str] = Query(None),
    client_category: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    sort_by: str = Query("client_name"),
    sort_order: str = Query("asc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    export: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.OPERATOR])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Per-client breakdown: contacts, leads, emails sent, replies, bounces, placements, unsubs."""

    # --- Pass 1: paginate ClientInfo ---
    client_q = db.query(ClientInfo)
    client_q = tenant_filter(client_q, ClientInfo, tenant_id)

    if search:
        client_q = client_q.filter(ClientInfo.client_name.ilike(f"%{search}%"))
    if industry:
        client_q = client_q.filter(ClientInfo.industry == industry)
    if client_category:
        client_q = client_q.filter(ClientInfo.client_category == client_category)

    total = client_q.count()

    if export:
        clients = client_q.order_by(ClientInfo.client_name).limit(EXPORT_CAP).all()
    else:
        offset = (page - 1) * page_size
        clients = client_q.order_by(ClientInfo.client_name).offset(offset).limit(page_size).all()

    if not clients:
        return {"items": [], "total": total, "page": page, "page_size": page_size,
                "pages": (total + page_size - 1) // page_size if page_size else 0}

    client_names = [c.client_name for c in clients]
    client_id_map = {c.client_name: c.client_id for c in clients}

    # Date filters for outreach
    date_filters = []
    if date_from:
        date_filters.append(OutreachEvent.sent_at >= datetime.strptime(date_from, "%Y-%m-%d"))
    if date_to:
        date_filters.append(OutreachEvent.sent_at <= datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1))

    # --- Pass 2: batch aggregates ---

    # Contacts per client_name
    contacts_q = db.query(
        ContactDetails.client_name,
        func.count(ContactDetails.contact_id).label("cnt"),
    ).filter(ContactDetails.client_name.in_(client_names))
    contacts_q = tenant_filter(contacts_q, ContactDetails, tenant_id)
    contacts_map = {r[0]: r[1] for r in contacts_q.group_by(ContactDetails.client_name).all()}

    # Leads per client_name
    leads_q = db.query(
        LeadDetails.client_name,
        func.count(LeadDetails.lead_id).label("cnt"),
    ).filter(LeadDetails.client_name.in_(client_names))
    leads_q = tenant_filter(leads_q, LeadDetails, tenant_id)
    leads_map = {r[0]: r[1] for r in leads_q.group_by(LeadDetails.client_name).all()}

    # Outreach stats per client_name (via ContactDetails join)
    outreach_base = db.query(
        ContactDetails.client_name,
        func.count(OutreachEvent.event_id).label("sent"),
        func.sum(case((OutreachEvent.status == OutreachStatus.REPLIED, 1), else_=0)).label("replied"),
        func.sum(case((OutreachEvent.status == OutreachStatus.BOUNCED, 1), else_=0)).label("bounced"),
    ).join(
        ContactDetails, OutreachEvent.contact_id == ContactDetails.contact_id
    ).filter(
        ContactDetails.client_name.in_(client_names),
        OutreachEvent.status.in_([OutreachStatus.SENT, OutreachStatus.REPLIED, OutreachStatus.BOUNCED]),
    )
    outreach_base = tenant_filter(outreach_base, OutreachEvent, tenant_id)
    for f in date_filters:
        outreach_base = outreach_base.filter(f)
    outreach_rows = outreach_base.group_by(ContactDetails.client_name).all()
    outreach_map = {r[0]: {"sent": r[1] or 0, "replied": r[2] or 0, "bounced": r[3] or 0} for r in outreach_rows}

    # Placements (deals won) per client_id
    client_ids = [cid for cid in client_id_map.values() if cid]
    placements_map_by_id: dict = {}
    if client_ids:
        place_q = db.query(
            Deal.client_id,
            func.count(Deal.deal_id).label("cnt"),
        ).filter(
            Deal.client_id.in_(client_ids),
            Deal.won_at.isnot(None),
            Deal.is_archived == False,
        )
        place_q = tenant_filter(place_q, Deal, tenant_id)
        placements_map_by_id = {r[0]: r[1] for r in place_q.group_by(Deal.client_id).all()}

    # Unsubs per client_name
    unsub_q = db.query(
        ContactDetails.client_name,
        func.count(ContactDetails.contact_id).label("cnt"),
    ).filter(
        ContactDetails.client_name.in_(client_names),
        ContactDetails.unsubscribed_at.isnot(None),
    )
    unsub_q = tenant_filter(unsub_q, ContactDetails, tenant_id)
    unsub_map = {r[0]: r[1] for r in unsub_q.group_by(ContactDetails.client_name).all()}

    # --- Merge ---
    items = []
    for c in clients:
        o = outreach_map.get(c.client_name, {"sent": 0, "replied": 0, "bounced": 0})
        sent = o["sent"]
        replied = o["replied"]
        bounced = o["bounced"]
        placements = placements_map_by_id.get(c.client_id, 0)
        items.append({
            "client_name": c.client_name,
            "industry": c.industry,
            "client_category": c.client_category.value if c.client_category else None,
            "contacts": contacts_map.get(c.client_name, 0),
            "leads": leads_map.get(c.client_name, 0),
            "sent": sent,
            "replied": replied,
            "reply_rate": round(replied / sent * 100, 1) if sent else 0,
            "bounced": bounced,
            "bounce_rate": round(bounced / sent * 100, 1) if sent else 0,
            "placements": placements,
            "placement_rate": round(placements / sent * 100, 1) if sent else 0,
            "unsubscribed": unsub_map.get(c.client_name, 0),
        })

    # Python sort (stats computed in-memory)
    sort_key = sort_by if sort_by in (
        "client_name", "contacts", "leads", "sent", "replied", "reply_rate",
        "bounced", "bounce_rate", "placements", "placement_rate", "unsubscribed",
    ) else "client_name"
    reverse = sort_order.lower() == "desc"
    items.sort(key=lambda x: (x.get(sort_key) or 0) if sort_key != "client_name" else (x.get(sort_key) or "").lower(), reverse=reverse)

    pages = (total + page_size - 1) // page_size if page_size else 0
    return {"items": items, "total": total, "page": page, "page_size": page_size, "pages": pages}


# ---------------------------------------------------------------------------
# Tab 2: Campaign Performance
# ---------------------------------------------------------------------------

@router.get("/campaign-performance")
def campaign_performance(
    search: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    sort_by: str = Query("created_at"),
    sort_order: str = Query("desc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    export: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.OPERATOR])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Per-campaign metrics using denormalized counters."""

    q = db.query(Campaign).filter(Campaign.is_archived == False)
    q = tenant_filter(q, Campaign, tenant_id)

    if search:
        q = q.filter(Campaign.name.ilike(f"%{search}%"))
    if status:
        q = q.filter(Campaign.status == status)
    if date_from:
        q = q.filter(Campaign.created_at >= datetime.strptime(date_from, "%Y-%m-%d"))
    if date_to:
        q = q.filter(Campaign.created_at <= datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1))

    # Sort
    sort_col_map = {
        "name": Campaign.name,
        "status": Campaign.status,
        "total_contacts": Campaign.total_contacts,
        "sent": Campaign.total_sent,
        "total_opened": Campaign.total_opened,
        "total_replied": Campaign.total_replied,
        "total_bounced": Campaign.total_bounced,
        "health_score": Campaign.health_score,
        "created_at": Campaign.created_at,
    }
    col = sort_col_map.get(sort_by, Campaign.created_at)
    q = q.order_by(col.desc() if sort_order.lower() == "desc" else col.asc())

    total = q.count()
    if export:
        campaigns = q.limit(EXPORT_CAP).all()
    else:
        campaigns = q.offset((page - 1) * page_size).limit(page_size).all()

    # Batch-load unsubs per campaign
    cids = [c.campaign_id for c in campaigns]
    unsub_map: dict = {}
    if cids:
        unsub_q = db.query(
            CampaignContact.campaign_id,
            func.count(CampaignContact.id).label("cnt"),
        ).filter(
            CampaignContact.campaign_id.in_(cids),
            CampaignContact.status == CampaignContactStatus.UNSUBSCRIBED,
        ).group_by(CampaignContact.campaign_id)
        unsub_map = {r[0]: r[1] for r in unsub_q.all()}

    items = []
    for c in campaigns:
        sent = c.total_sent or 0
        opened = c.total_opened or 0
        replied = c.total_replied or 0
        bounced = c.total_bounced or 0
        items.append({
            "campaign_id": c.campaign_id,
            "name": c.name,
            "status": c.status.value if c.status else "draft",
            "total_contacts": c.total_contacts or 0,
            "sent": sent,
            "opened": opened,
            "open_rate": round(opened / sent * 100, 1) if sent else 0,
            "replied": replied,
            "reply_rate": round(replied / sent * 100, 1) if sent else 0,
            "bounced": bounced,
            "bounce_rate": round(bounced / sent * 100, 1) if sent else 0,
            "unsubscribed": unsub_map.get(c.campaign_id, 0),
            "health_score": c.health_score,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        })

    pages = (total + page_size - 1) // page_size if page_size else 0
    return {"items": items, "total": total, "page": page, "page_size": page_size, "pages": pages}


# ---------------------------------------------------------------------------
# Tab 3: Mailbox Health
# ---------------------------------------------------------------------------

@router.get("/mailbox-health")
def mailbox_health(
    search: Optional[str] = Query(None),
    warmup_status: Optional[str] = Query(None),
    sort_by: str = Query("email"),
    sort_order: str = Query("asc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    export: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.OPERATOR])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Per-mailbox stats from SenderMailbox model."""

    q = db.query(SenderMailbox)
    q = tenant_filter(q, SenderMailbox, tenant_id)

    if search:
        q = q.filter(SenderMailbox.email.ilike(f"%{search}%"))
    if warmup_status:
        q = q.filter(SenderMailbox.warmup_status == warmup_status)

    sort_col_map = {
        "email": SenderMailbox.email,
        "warmup_status": SenderMailbox.warmup_status,
        "connection_status": SenderMailbox.connection_status,
        "emails_sent_today": SenderMailbox.emails_sent_today,
        "total_emails_sent": SenderMailbox.total_emails_sent,
        "bounce_count": SenderMailbox.bounce_count,
        "reply_count": SenderMailbox.reply_count,
        "complaint_count": SenderMailbox.complaint_count,
    }
    col = sort_col_map.get(sort_by, SenderMailbox.email)
    q = q.order_by(col.desc() if sort_order.lower() == "desc" else col.asc())

    total = q.count()
    if export:
        mailboxes = q.limit(EXPORT_CAP).all()
    else:
        mailboxes = q.offset((page - 1) * page_size).limit(page_size).all()

    items = []
    for m in mailboxes:
        total_sent = m.total_emails_sent or 0
        bounces = m.bounce_count or 0
        complaints = m.complaint_count or 0
        items.append({
            "mailbox_id": m.mailbox_id,
            "email": m.email,
            "provider": m.provider.value if m.provider else None,
            "warmup_status": m.warmup_status.value if m.warmup_status else None,
            "connection_status": m.connection_status or "untested",
            "emails_sent_today": m.emails_sent_today or 0,
            "daily_send_limit": m.daily_send_limit or 30,
            "total_emails_sent": total_sent,
            "bounce_count": bounces,
            "bounce_rate": round(bounces / total_sent * 100, 1) if total_sent else 0,
            "reply_count": m.reply_count or 0,
            "complaint_count": complaints,
            "complaint_rate": round(complaints / total_sent * 100, 1) if total_sent else 0,
        })

    pages = (total + page_size - 1) // page_size if page_size else 0
    return {"items": items, "total": total, "page": page, "page_size": page_size, "pages": pages}


# ---------------------------------------------------------------------------
# Tab 4: Daily Activity
# ---------------------------------------------------------------------------

@router.get("/daily-activity")
def daily_activity(
    days: int = Query(30, ge=7, le=180),
    granularity: str = Query("daily"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.OPERATOR])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Time-series aggregates: sent, opened, replied, bounced per day/week."""
    cutoff = datetime.utcnow() - timedelta(days=days)

    q = db.query(
        func.date(OutreachEvent.sent_at).label("day"),
        func.count(OutreachEvent.event_id).label("sent"),
        func.sum(case((OutreachEvent.opened_at.isnot(None), 1), else_=0)).label("opened"),
        func.sum(case((OutreachEvent.status == OutreachStatus.REPLIED, 1), else_=0)).label("replied"),
        func.sum(case((OutreachEvent.status == OutreachStatus.BOUNCED, 1), else_=0)).label("bounced"),
    ).filter(
        OutreachEvent.sent_at >= cutoff,
        OutreachEvent.status.in_([OutreachStatus.SENT, OutreachStatus.REPLIED, OutreachStatus.BOUNCED]),
    )
    q = tenant_filter(q, OutreachEvent, tenant_id)
    rows = q.group_by(func.date(OutreachEvent.sent_at)).order_by(func.date(OutreachEvent.sent_at)).all()

    # If weekly granularity, aggregate days into weeks
    if granularity == "weekly" and rows:
        from collections import defaultdict
        weekly: dict = defaultdict(lambda: {"sent": 0, "opened": 0, "replied": 0, "bounced": 0})
        for r in rows:
            day = r.day if isinstance(r.day, str) else str(r.day)
            dt = datetime.strptime(day, "%Y-%m-%d")
            week_start = (dt - timedelta(days=dt.weekday())).strftime("%Y-%m-%d")
            weekly[week_start]["sent"] += int(r.sent or 0)
            weekly[week_start]["opened"] += int(r.opened or 0)
            weekly[week_start]["replied"] += int(r.replied or 0)
            weekly[week_start]["bounced"] += int(r.bounced or 0)
        series = [{"date": k, **v} for k, v in sorted(weekly.items())]
    else:
        series = [
            {
                "date": r.day if isinstance(r.day, str) else str(r.day),
                "sent": int(r.sent or 0),
                "opened": int(r.opened or 0),
                "replied": int(r.replied or 0),
                "bounced": int(r.bounced or 0),
            }
            for r in rows
        ]

    totals = {
        "sent": sum(s["sent"] for s in series),
        "opened": sum(s["opened"] for s in series),
        "replied": sum(s["replied"] for s in series),
        "bounced": sum(s["bounced"] for s in series),
    }
    return {"days": days, "granularity": granularity, "series": series, "totals": totals}


# ---------------------------------------------------------------------------
# Tab 5: Contact Engagement
# ---------------------------------------------------------------------------

@router.get("/contact-engagement")
def contact_engagement(
    search: Optional[str] = Query(None),
    client_name: Optional[str] = Query(None),
    min_emails: int = Query(0, ge=0),
    has_replied: Optional[bool] = Query(None),
    sort_by: str = Query("sent"),
    sort_order: str = Query("desc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    export: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.OPERATOR])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Per-contact outreach summary."""

    q = db.query(
        ContactDetails.contact_id,
        ContactDetails.first_name,
        ContactDetails.last_name,
        ContactDetails.email,
        ContactDetails.client_name,
        ContactDetails.outreach_status,
        func.count(OutreachEvent.event_id).label("sent"),
        func.sum(case((OutreachEvent.opened_at.isnot(None), 1), else_=0)).label("opens"),
        func.sum(case((OutreachEvent.status == OutreachStatus.REPLIED, 1), else_=0)).label("replies"),
        func.max(OutreachEvent.sent_at).label("last_activity"),
    ).outerjoin(
        OutreachEvent, OutreachEvent.contact_id == ContactDetails.contact_id
    )
    q = tenant_filter(q, ContactDetails, tenant_id)

    if search:
        q = q.filter(
            (ContactDetails.first_name.ilike(f"%{search}%"))
            | (ContactDetails.last_name.ilike(f"%{search}%"))
            | (ContactDetails.email.ilike(f"%{search}%"))
        )
    if client_name:
        q = q.filter(ContactDetails.client_name == client_name)

    q = q.group_by(
        ContactDetails.contact_id,
        ContactDetails.first_name,
        ContactDetails.last_name,
        ContactDetails.email,
        ContactDetails.client_name,
        ContactDetails.outreach_status,
    )

    if min_emails > 0:
        q = q.having(func.count(OutreachEvent.event_id) >= min_emails)
    if has_replied is True:
        q = q.having(func.sum(case((OutreachEvent.status == OutreachStatus.REPLIED, 1), else_=0)) > 0)
    elif has_replied is False:
        q = q.having(func.sum(case((OutreachEvent.status == OutreachStatus.REPLIED, 1), else_=0)) == 0)

    # Sorting
    sort_col_map = {
        "name": ContactDetails.first_name,
        "email": ContactDetails.email,
        "company": ContactDetails.client_name,
        "sent": func.count(OutreachEvent.event_id),
        "opens": func.sum(case((OutreachEvent.opened_at.isnot(None), 1), else_=0)),
        "replies": func.sum(case((OutreachEvent.status == OutreachStatus.REPLIED, 1), else_=0)),
        "last_activity": func.max(OutreachEvent.sent_at),
    }
    order_expr = sort_col_map.get(sort_by, func.count(OutreachEvent.event_id))
    q = q.order_by(order_expr.desc() if sort_order.lower() == "desc" else order_expr.asc())

    # We need total count from a subquery
    from sqlalchemy import text
    count_sub = q.subquery()
    total = db.query(func.count()).select_from(count_sub).scalar() or 0

    if export:
        rows = q.limit(EXPORT_CAP).all()
    else:
        rows = q.offset((page - 1) * page_size).limit(page_size).all()

    items = []
    for r in rows:
        items.append({
            "contact_id": r.contact_id,
            "name": f"{r.first_name or ''} {r.last_name or ''}".strip(),
            "email": r.email,
            "company": r.client_name,
            "status": r.outreach_status.value if r.outreach_status else "active",
            "sent": int(r.sent or 0),
            "opens": int(r.opens or 0),
            "replies": int(r.replies or 0),
            "last_activity": r.last_activity.isoformat() if r.last_activity else None,
        })

    pages = (total + page_size - 1) // page_size if page_size else 0
    return {"items": items, "total": total, "page": page, "page_size": page_size, "pages": pages}


# ---------------------------------------------------------------------------
# Tab 6: Domain Deliverability
# ---------------------------------------------------------------------------

@router.get("/domain-deliverability")
def domain_deliverability(
    days: int = Query(30, ge=7, le=180),
    sort_by: str = Query("sent"),
    sort_order: str = Query("desc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    export: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.OPERATOR])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Recipient-domain-level deliverability stats."""
    cutoff = datetime.utcnow() - timedelta(days=days)

    # Domain extraction: MySQL vs SQLite
    if settings.DB_TYPE == "sqlite":
        domain_expr = func.substr(
            ContactDetails.email,
            func.instr(ContactDetails.email, "@") + 1,
        )
    else:
        domain_expr = func.substring_index(ContactDetails.email, "@", -1)

    q = db.query(
        domain_expr.label("domain"),
        func.count(OutreachEvent.event_id).label("sent"),
        func.sum(case((OutreachEvent.opened_at.isnot(None), 1), else_=0)).label("opened"),
        func.sum(case((OutreachEvent.status == OutreachStatus.REPLIED, 1), else_=0)).label("replied"),
        func.sum(case((OutreachEvent.status == OutreachStatus.BOUNCED, 1), else_=0)).label("bounced"),
    ).join(
        ContactDetails, OutreachEvent.contact_id == ContactDetails.contact_id,
    ).filter(
        OutreachEvent.sent_at >= cutoff,
        OutreachEvent.status.in_([OutreachStatus.SENT, OutreachStatus.REPLIED, OutreachStatus.BOUNCED]),
    )
    q = tenant_filter(q, OutreachEvent, tenant_id)
    q = q.group_by(domain_expr)

    # Sort
    sort_map = {
        "domain": domain_expr,
        "sent": func.count(OutreachEvent.event_id),
        "opened": func.sum(case((OutreachEvent.opened_at.isnot(None), 1), else_=0)),
        "replied": func.sum(case((OutreachEvent.status == OutreachStatus.REPLIED, 1), else_=0)),
        "bounced": func.sum(case((OutreachEvent.status == OutreachStatus.BOUNCED, 1), else_=0)),
    }
    order_expr = sort_map.get(sort_by, func.count(OutreachEvent.event_id))
    q = q.order_by(order_expr.desc() if sort_order.lower() == "desc" else order_expr.asc())

    count_sub = q.subquery()
    total = db.query(func.count()).select_from(count_sub).scalar() or 0

    if export:
        rows = q.limit(EXPORT_CAP).all()
    else:
        rows = q.offset((page - 1) * page_size).limit(page_size).all()

    items = []
    for r in rows:
        sent = int(r.sent or 0)
        opened = int(r.opened or 0)
        replied = int(r.replied or 0)
        bounced = int(r.bounced or 0)
        items.append({
            "domain": r.domain,
            "sent": sent,
            "opened": opened,
            "open_rate": round(opened / sent * 100, 1) if sent else 0,
            "replied": replied,
            "reply_rate": round(replied / sent * 100, 1) if sent else 0,
            "bounced": bounced,
            "bounce_rate": round(bounced / sent * 100, 1) if sent else 0,
        })

    pages = (total + page_size - 1) // page_size if page_size else 0
    return {"items": items, "total": total, "page": page, "page_size": page_size, "pages": pages}
