"""Automation Activity API — exposes system automation events to users."""
import json
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from app.api.deps.database import get_db
from app.api.deps.auth import get_current_active_user
from app.db.models.user import User
from app.db.models.automation_event import AutomationEvent

router = APIRouter(prefix="/automation", tags=["automation"])


@router.get("/events")
def list_events(
    event_type: Optional[str] = None,
    status: Optional[str] = None,
    hours: int = Query(24, ge=1, le=168),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """List recent automation events (paginated, filterable)."""
    since = datetime.utcnow() - timedelta(hours=hours)
    query = db.query(AutomationEvent).filter(AutomationEvent.created_at >= since)

    if event_type:
        query = query.filter(AutomationEvent.event_type == event_type)
    if status:
        query = query.filter(AutomationEvent.status == status)

    total = query.count()
    events = query.order_by(desc(AutomationEvent.created_at)).offset(
        (page - 1) * page_size
    ).limit(page_size).all()

    return {
        "items": [
            {
                "event_id": e.event_id,
                "event_type": e.event_type,
                "source": e.source,
                "title": e.title,
                "details": json.loads(e.details_json) if e.details_json else None,
                "status": e.status,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in events
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size if total > 0 else 0,
    }


@router.get("/events/summary")
def events_summary(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """Last 24h summary — counts by event type and status."""
    since = datetime.utcnow() - timedelta(hours=24)
    rows = db.query(
        AutomationEvent.event_type,
        AutomationEvent.status,
        func.count(AutomationEvent.event_id),
    ).filter(
        AutomationEvent.created_at >= since,
    ).group_by(
        AutomationEvent.event_type,
        AutomationEvent.status,
    ).all()

    by_type: dict = {}
    total = 0
    errors = 0
    for event_type, status, count in rows:
        by_type.setdefault(event_type, {"total": 0, "success": 0, "error": 0, "skipped": 0})
        by_type[event_type]["total"] += count
        by_type[event_type][status] = by_type[event_type].get(status, 0) + count
        total += count
        if status == "error":
            errors += count

    # Latest event
    latest = db.query(AutomationEvent).filter(
        AutomationEvent.created_at >= since,
    ).order_by(desc(AutomationEvent.created_at)).first()

    return {
        "period_hours": 24,
        "total_events": total,
        "total_errors": errors,
        "by_type": by_type,
        "latest_event": {
            "title": latest.title,
            "event_type": latest.event_type,
            "status": latest.status,
            "created_at": latest.created_at.isoformat() if latest.created_at else None,
        } if latest else None,
    }
