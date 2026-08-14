"""Visitor tracking endpoints — page view tracking and analytics."""
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from pydantic import BaseModel

from app.db.base import get_db
from app.api.deps.auth import require_role, get_current_tenant_id
from app.db.models.user import User, UserRole
from app.db.models.visitor import VisitorEvent

router = APIRouter(prefix="/visitors", tags=["Visitor Tracking"])


class TrackVisitRequest(BaseModel):
    visitor_id: str
    page_url: str
    referrer: Optional[str] = None
    company_name: Optional[str] = None
    company_domain: Optional[str] = None
    metadata_json: Optional[str] = None


@router.get("")
def list_visitors(
    visitor_id: Optional[str] = None,
    company_name: Optional[str] = None,
    days: int = Query(30, ge=1, le=90),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.BDM])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """List visitor events with optional filters."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    q = db.query(VisitorEvent).filter(
        VisitorEvent.is_archived == False,
        VisitorEvent.visited_at >= cutoff,
    )
    # VisitorEvent does not have tenant_id in the existing model,
    # so we skip tenant_filter for visitor events
    # (they are public page-view events tracked by a JS pixel)

    if visitor_id:
        q = q.filter(VisitorEvent.visitor_id == visitor_id)
    if company_name:
        q = q.filter(VisitorEvent.company_name.ilike(f"%{company_name}%"))

    total = q.count()
    items = q.order_by(desc(VisitorEvent.visited_at)).offset(
        (page - 1) * page_size
    ).limit(page_size).all()

    return {
        "items": [
            {
                "event_id": v.event_id,
                "visitor_id": v.visitor_id,
                "contact_id": v.contact_id,
                "page_url": v.page_url,
                "referrer": v.referrer,
                "ip_address": v.ip_address,
                "user_agent": v.user_agent,
                "company_name": v.company_name,
                "company_domain": v.company_domain,
                "visited_at": v.visited_at.isoformat() if v.visited_at else None,
            }
            for v in items
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/stats")
def visitor_stats(
    days: int = Query(30, ge=1, le=90),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.BDM])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Get visitor statistics."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    base_q = db.query(VisitorEvent).filter(
        VisitorEvent.is_archived == False,
        VisitorEvent.visited_at >= cutoff,
    )

    total_events = base_q.count()
    unique_visitors = base_q.with_entities(
        func.count(func.distinct(VisitorEvent.visitor_id))
    ).scalar() or 0

    # Top pages
    top_pages_rows = base_q.with_entities(
        VisitorEvent.page_url,
        func.count(VisitorEvent.event_id).label("views"),
    ).group_by(VisitorEvent.page_url).order_by(
        desc("views")
    ).limit(10).all()

    top_pages = [{"page_url": p, "views": v} for p, v in top_pages_rows]

    # Top companies (identified visitors)
    top_companies_rows = base_q.filter(
        VisitorEvent.company_name.isnot(None),
        VisitorEvent.company_name != "",
    ).with_entities(
        VisitorEvent.company_name,
        func.count(VisitorEvent.event_id).label("visits"),
    ).group_by(VisitorEvent.company_name).order_by(
        desc("visits")
    ).limit(10).all()

    top_companies = [{"company_name": c, "visits": v} for c, v in top_companies_rows]

    # Daily trend
    daily_rows = base_q.with_entities(
        func.date(VisitorEvent.visited_at).label("day"),
        func.count(VisitorEvent.event_id).label("events"),
        func.count(func.distinct(VisitorEvent.visitor_id)).label("unique"),
    ).group_by("day").order_by("day").all()

    daily_trend = [
        {"date": str(row.day), "events": row.events, "unique_visitors": row.unique}
        for row in daily_rows
    ]

    return {
        "period_days": days,
        "total_events": total_events,
        "unique_visitors": unique_visitors,
        "top_pages": top_pages,
        "top_companies": top_companies,
        "daily_trend": daily_trend,
    }


@router.post("/track")
def track_visit(
    body: TrackVisitRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Track a page visit (no auth required -- called by JS pixel)."""
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent", "")[:500]

    event = VisitorEvent(
        visitor_id=body.visitor_id,
        page_url=body.page_url[:1000],
        referrer=body.referrer[:1000] if body.referrer else None,
        ip_address=ip_address,
        user_agent=user_agent,
        company_name=body.company_name,
        company_domain=body.company_domain,
        metadata_json=body.metadata_json,
        visited_at=datetime.utcnow(),
    )
    db.add(event)
    db.commit()

    return {"ok": True, "event_id": event.event_id}


@router.get("/pixel.js")
def serve_tracking_pixel():
    """Serve the tracking pixel JavaScript snippet."""
    js_content = """
(function() {
    var visitorId = localStorage.getItem('_nl_vid');
    if (!visitorId) {
        visitorId = 'v_' + Math.random().toString(36).substr(2, 9) + Date.now().toString(36);
        localStorage.setItem('_nl_vid', visitorId);
    }
    var data = {
        visitor_id: visitorId,
        page_url: window.location.href,
        referrer: document.referrer || null
    };
    fetch('/api/v1/visitors/track', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(data)
    }).catch(function() {});
})();
"""
    return Response(
        content=js_content.strip(),
        media_type="application/javascript",
        headers={"Cache-Control": "public, max-age=3600"},
    )
