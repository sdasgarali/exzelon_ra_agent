"""Calendar booking CRUD endpoints."""
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from pydantic import BaseModel

from app.db.base import get_db
from app.api.deps.auth import get_current_active_user, require_role, get_current_tenant_id, ensure_tenant
from app.db.query_helpers import tenant_filter
from app.db.models.user import User, UserRole
from app.db.models.calendar_booking import CalendarBooking

router = APIRouter(prefix="/calendar", tags=["Calendar"])


class BookingCreate(BaseModel):
    contact_id: Optional[int] = None
    deal_id: Optional[int] = None
    campaign_id: Optional[int] = None
    provider: str = "manual"  # calendly/cal_com/manual
    booking_url: Optional[str] = None
    event_type: Optional[str] = None
    scheduled_at: Optional[str] = None  # ISO datetime
    duration_minutes: int = 30
    attendee_email: Optional[str] = None
    attendee_name: Optional[str] = None
    status: str = "scheduled"
    external_id: Optional[str] = None
    notes: Optional[str] = None


class BookingUpdate(BaseModel):
    contact_id: Optional[int] = None
    deal_id: Optional[int] = None
    campaign_id: Optional[int] = None
    provider: Optional[str] = None
    booking_url: Optional[str] = None
    event_type: Optional[str] = None
    scheduled_at: Optional[str] = None
    duration_minutes: Optional[int] = None
    attendee_email: Optional[str] = None
    attendee_name: Optional[str] = None
    status: Optional[str] = None
    external_id: Optional[str] = None
    notes: Optional[str] = None


def _booking_to_dict(b: CalendarBooking) -> dict:
    return {
        "booking_id": b.booking_id,
        "tenant_id": b.tenant_id,
        "contact_id": b.contact_id,
        "deal_id": b.deal_id,
        "campaign_id": b.campaign_id,
        "provider": b.provider,
        "booking_url": b.booking_url,
        "event_type": b.event_type,
        "scheduled_at": b.scheduled_at.isoformat() if b.scheduled_at else None,
        "duration_minutes": b.duration_minutes,
        "attendee_email": b.attendee_email,
        "attendee_name": b.attendee_name,
        "status": b.status,
        "external_id": b.external_id,
        "notes": b.notes,
        "created_at": b.created_at.isoformat() if b.created_at else None,
        "updated_at": b.updated_at.isoformat() if b.updated_at else None,
    }


@router.get("/bookings")
def list_bookings(
    status: Optional[str] = None,
    contact_id: Optional[int] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """List calendar bookings with optional filters."""
    q = db.query(CalendarBooking).filter(CalendarBooking.is_archived == False)
    q = tenant_filter(q, CalendarBooking, tenant_id)

    if status:
        q = q.filter(CalendarBooking.status == status)
    if contact_id:
        q = q.filter(CalendarBooking.contact_id == contact_id)

    total = q.count()
    items = q.order_by(desc(CalendarBooking.scheduled_at)).offset(
        (page - 1) * page_size
    ).limit(page_size).all()

    return {
        "items": [_booking_to_dict(b) for b in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("/bookings")
def create_booking(
    body: BookingCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.BDM])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Create a calendar booking."""
    scheduled_dt = None
    if body.scheduled_at:
        try:
            scheduled_dt = datetime.fromisoformat(body.scheduled_at)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid scheduled_at format. Use ISO datetime.")

    booking = CalendarBooking(
        tenant_id=ensure_tenant(tenant_id),
        contact_id=body.contact_id,
        deal_id=body.deal_id,
        campaign_id=body.campaign_id,
        provider=body.provider,
        booking_url=body.booking_url,
        event_type=body.event_type,
        scheduled_at=scheduled_dt,
        duration_minutes=body.duration_minutes,
        attendee_email=body.attendee_email,
        attendee_name=body.attendee_name,
        status=body.status,
        external_id=body.external_id,
        notes=body.notes,
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)
    return _booking_to_dict(booking)


@router.put("/bookings/{booking_id}")
def update_booking(
    booking_id: int,
    body: BookingUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.BDM])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Update a calendar booking."""
    q = db.query(CalendarBooking).filter(
        CalendarBooking.booking_id == booking_id,
        CalendarBooking.is_archived == False,
    )
    q = tenant_filter(q, CalendarBooking, tenant_id)
    booking = q.first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    if body.contact_id is not None:
        booking.contact_id = body.contact_id
    if body.deal_id is not None:
        booking.deal_id = body.deal_id
    if body.campaign_id is not None:
        booking.campaign_id = body.campaign_id
    if body.provider is not None:
        booking.provider = body.provider
    if body.booking_url is not None:
        booking.booking_url = body.booking_url
    if body.event_type is not None:
        booking.event_type = body.event_type
    if body.scheduled_at is not None:
        try:
            booking.scheduled_at = datetime.fromisoformat(body.scheduled_at) if body.scheduled_at else None
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid scheduled_at format")
    if body.duration_minutes is not None:
        booking.duration_minutes = body.duration_minutes
    if body.attendee_email is not None:
        booking.attendee_email = body.attendee_email
    if body.attendee_name is not None:
        booking.attendee_name = body.attendee_name
    if body.status is not None:
        booking.status = body.status
    if body.external_id is not None:
        booking.external_id = body.external_id
    if body.notes is not None:
        booking.notes = body.notes

    db.commit()
    db.refresh(booking)
    return _booking_to_dict(booking)


@router.delete("/bookings/{booking_id}")
def delete_booking(
    booking_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.BDM])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Soft-delete a calendar booking."""
    q = db.query(CalendarBooking).filter(
        CalendarBooking.booking_id == booking_id,
        CalendarBooking.is_archived == False,
    )
    q = tenant_filter(q, CalendarBooking, tenant_id)
    booking = q.first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    booking.is_archived = True
    db.commit()
    return {"ok": True, "booking_id": booking_id}


@router.get("/bookings/stats")
def booking_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Get booking statistics by status."""
    base_q = db.query(CalendarBooking).filter(CalendarBooking.is_archived == False)
    base_q = tenant_filter(base_q, CalendarBooking, tenant_id)

    total = base_q.count()

    by_status_rows = base_q.with_entities(
        CalendarBooking.status,
        func.count(CalendarBooking.booking_id),
    ).group_by(CalendarBooking.status).all()

    by_status = {s: c for s, c in by_status_rows}

    return {
        "total": total,
        "by_status": by_status,
    }
