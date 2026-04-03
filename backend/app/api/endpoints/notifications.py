"""Notification center endpoints."""
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from app.db.base import get_db
from app.api.deps.auth import get_current_active_user, get_current_tenant_id
from app.db.query_helpers import tenant_filter
from app.db.models.user import User
from app.db.models.notification import NotificationEntry

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("")
def list_notifications(
    category: Optional[str] = None,
    is_read: Optional[bool] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """List notifications for the current user (targeted + broadcast)."""
    q = db.query(NotificationEntry).filter(NotificationEntry.is_archived == False)
    q = tenant_filter(q, NotificationEntry, tenant_id)
    # Show notifications targeted to this user OR broadcast (user_id=None)
    q = q.filter(
        (NotificationEntry.user_id == user.user_id) | (NotificationEntry.user_id == None)  # noqa: E711
    )
    if category:
        q = q.filter(NotificationEntry.category == category)
    if is_read is not None:
        q = q.filter(NotificationEntry.is_read == is_read)

    total = q.count()

    # Count unread before pagination
    unread_q = db.query(func.count(NotificationEntry.notification_id)).filter(
        NotificationEntry.is_archived == False,
        NotificationEntry.is_read == False,
    )
    unread_q = tenant_filter(unread_q, NotificationEntry, tenant_id)
    unread_q = unread_q.filter(
        (NotificationEntry.user_id == user.user_id) | (NotificationEntry.user_id == None)  # noqa: E711
    )
    unread_count = unread_q.scalar() or 0

    items = q.order_by(desc(NotificationEntry.created_at)).offset(
        (page - 1) * page_size
    ).limit(page_size).all()

    return {
        "items": [
            {
                "notification_id": n.notification_id,
                "title": n.title,
                "message": n.message,
                "category": n.category,
                "priority": n.priority,
                "link": n.link,
                "is_read": n.is_read,
                "created_at": n.created_at.isoformat() if n.created_at else None,
            }
            for n in items
        ],
        "total": total,
        "unread_count": unread_count,
    }


@router.get("/unread-count")
def unread_count(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Get the count of unread notifications for the current user."""
    q = db.query(func.count(NotificationEntry.notification_id)).filter(
        NotificationEntry.is_archived == False,
        NotificationEntry.is_read == False,
    )
    q = tenant_filter(q, NotificationEntry, tenant_id)
    q = q.filter(
        (NotificationEntry.user_id == user.user_id) | (NotificationEntry.user_id == None)  # noqa: E711
    )
    return {"unread_count": q.scalar() or 0}


@router.put("/{notification_id}/read")
def mark_read(
    notification_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Mark a single notification as read."""
    q = db.query(NotificationEntry).filter(
        NotificationEntry.notification_id == notification_id,
        NotificationEntry.is_archived == False,
    )
    q = tenant_filter(q, NotificationEntry, tenant_id)
    q = q.filter(
        (NotificationEntry.user_id == user.user_id) | (NotificationEntry.user_id == None)  # noqa: E711
    )
    n = q.first()
    if n:
        n.is_read = True
        n.read_at = datetime.utcnow()
        db.commit()
    return {"ok": True}


@router.put("/read-all")
def mark_all_read(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Mark all unread notifications as read for the current user."""
    q = db.query(NotificationEntry).filter(
        NotificationEntry.is_archived == False,
        NotificationEntry.is_read == False,
    )
    q = tenant_filter(q, NotificationEntry, tenant_id)
    q = q.filter(
        (NotificationEntry.user_id == user.user_id) | (NotificationEntry.user_id == None)  # noqa: E711
    )
    updated = q.update(
        {"is_read": True, "read_at": datetime.utcnow()},
        synchronize_session=False,
    )
    db.commit()
    return {"marked_read": updated}
