"""Outreach management endpoints."""
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.api.deps import get_db, get_current_active_user, require_role, get_current_tenant_id
from app.db.models.user import User, UserRole
from app.db.models.outreach import OutreachEvent, OutreachStatus, OutreachChannel
from app.db.models.contact import ContactDetails
from app.db.models.lead import LeadDetails
from app.db.models.sender_mailbox import SenderMailbox
from app.schemas.outreach import OutreachEventCreate, OutreachEventResponse, OutreachThreadResponse
from app.db.query_helpers import tenant_filter

router = APIRouter(prefix="/outreach", tags=["Outreach"])


@router.get("/events", response_model=List[OutreachEventResponse])
async def list_outreach_events(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    status_filter: Optional[OutreachStatus] = Query(None, alias="status"),
    channel: Optional[OutreachChannel] = None,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id)
):
    """List outreach events."""
    query = db.query(OutreachEvent)
    query = tenant_filter(query, OutreachEvent, tenant_id)

    if status_filter:
        query = query.filter(OutreachEvent.status == status_filter)
    if channel:
        query = query.filter(OutreachEvent.channel == channel)
    if from_date:
        query = query.filter(OutreachEvent.sent_at >= from_date)
    if to_date:
        query = query.filter(OutreachEvent.sent_at <= to_date)

    events = query.order_by(OutreachEvent.sent_at.desc()).offset(skip).limit(limit).all()
    return [OutreachEventResponse.model_validate(e) for e in events]


@router.get("/events/{event_id}", response_model=OutreachEventResponse)
async def get_outreach_event(
    event_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id)
):
    """Get outreach event by ID."""
    event = db.query(OutreachEvent).filter(OutreachEvent.event_id == event_id).first()
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Outreach event not found"
        )
    if tenant_id is not None and event.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Outreach event not found"
        )
    return OutreachEventResponse.model_validate(event)


@router.get("/events/{event_id}/thread")
async def get_outreach_thread(
    event_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id)
):
    """Get full thread/conversation view for an outreach event."""
    event = db.query(OutreachEvent).filter(OutreachEvent.event_id == event_id).first()
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Outreach event not found"
        )
    if tenant_id is not None and event.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Outreach event not found"
        )

    contact = db.query(ContactDetails).filter(
        ContactDetails.contact_id == event.contact_id
    ).first()

    lead = None
    if event.lead_id:
        lead = db.query(LeadDetails).filter(
            LeadDetails.lead_id == event.lead_id
        ).first()

    sender = None
    if event.sender_mailbox_id:
        sender = db.query(SenderMailbox).filter(
            SenderMailbox.mailbox_id == event.sender_mailbox_id
        ).first()

    return {
        "event_id": event.event_id,
        "contact_id": event.contact_id,
        "contact_name": f"{contact.first_name} {contact.last_name}" if contact else None,
        "contact_email": contact.email if contact else None,
        "client_name": (lead.client_name if lead else (contact.client_name if contact else None)),
        "job_title": lead.job_title if lead else None,
        "sender_email": sender.email if sender else None,
        "sender_name": sender.display_name if sender else None,
        "sent_at": event.sent_at.isoformat() if event.sent_at else None,
        "subject": event.subject,
        "body_html": event.body_html,
        "body_text": event.body_text,
        "status": event.status.value if event.status else None,
        "reply_detected_at": event.reply_detected_at.isoformat() if event.reply_detected_at else None,
        "reply_subject": event.reply_subject,
        "reply_body": event.reply_body,
        "message_id": event.message_id,
        "channel": event.channel.value if event.channel else None,
    }


@router.post("/events", response_model=OutreachEventResponse, status_code=status.HTTP_201_CREATED)
async def create_outreach_event(
    event_in: OutreachEventCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id)
):
    """Create an outreach event."""
    event = OutreachEvent(**event_in.model_dump())
    event.tenant_id = tenant_id or 1
    db.add(event)
    db.commit()
    db.refresh(event)

    return OutreachEventResponse.model_validate(event)


@router.delete("/events/bulk")
async def bulk_delete_outreach_events(
    request: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id)
):
    """Delete multiple outreach events by IDs. Admin/Operator only."""
    event_ids = request.get("event_ids", [])
    if not event_ids:
        raise HTTPException(status_code=400, detail="No event IDs provided")

    query = db.query(OutreachEvent).filter(OutreachEvent.event_id.in_(event_ids))
    query = tenant_filter(query, OutreachEvent, tenant_id)
    deleted_count = query.delete(synchronize_session=False)

    db.commit()

    return {
        "message": f"Successfully deleted {deleted_count} outreach event(s)",
        "deleted_count": deleted_count
    }


@router.delete("/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_outreach_event(
    event_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id)
):
    """Delete a single outreach event. Admin/Operator only."""
    event = db.query(OutreachEvent).filter(OutreachEvent.event_id == event_id).first()
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Outreach event not found"
        )
    if tenant_id is not None and event.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Outreach event not found"
        )
    db.delete(event)
    db.commit()


@router.post("/run-mailmerge")
async def run_mailmerge_export(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id)
):
    """Generate mail merge export package."""
    from app.services.pipelines.outreach import run_outreach_mailmerge_pipeline

    background_tasks.add_task(
        run_outreach_mailmerge_pipeline,
        triggered_by=current_user.email
    )

    return {
        "message": "Mail merge export started",
        "status": "processing"
    }


@router.post("/send-emails")
async def send_emails(
    background_tasks: BackgroundTasks,
    dry_run: bool = Query(True, description="If true, validate but don't send"),
    limit: int = Query(30, description="Max emails to send"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id)
):
    """Send emails programmatically (respects daily limits and cooldown)."""
    from app.services.pipelines.outreach import run_outreach_send_pipeline

    background_tasks.add_task(
        run_outreach_send_pipeline,
        dry_run=dry_run,
        limit=limit,
        triggered_by=current_user.email
    )

    return {
        "message": f"Email sending started (dry_run={dry_run}, limit={limit})",
        "status": "processing"
    }


@router.post("/check-replies")
async def check_replies(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id)
):
    """Manually trigger reply checking for all mailboxes."""
    from app.services.reply_tracker import check_all_mailbox_replies
    from app.db.base import SessionLocal

    def _run_check():
        check_db = SessionLocal()
        try:
            check_all_mailbox_replies(check_db)
        finally:
            check_db.close()

    background_tasks.add_task(_run_check)

    return {
        "message": "Reply checking started",
        "status": "processing"
    }


@router.get("/stats/summary")
async def get_outreach_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id)
):
    """Get outreach statistics summary."""
    query = db.query(OutreachEvent)
    query = tenant_filter(query, OutreachEvent, tenant_id)
    total = query.with_entities(func.count(OutreachEvent.event_id)).scalar()

    query = db.query(OutreachEvent)
    query = tenant_filter(query, OutreachEvent, tenant_id)
    by_status = query.with_entities(
        OutreachEvent.status,
        func.count(OutreachEvent.event_id)
    ).group_by(OutreachEvent.status).all()

    sent_count = next((c for s, c in by_status if s == OutreachStatus.SENT), 0)
    bounced_count = next((c for s, c in by_status if s == OutreachStatus.BOUNCED), 0)
    replied_count = next((c for s, c in by_status if s == OutreachStatus.REPLIED), 0)

    bounce_rate = (bounced_count / sent_count * 100) if sent_count > 0 else 0
    reply_rate = (replied_count / sent_count * 100) if sent_count > 0 else 0

    return {
        "total_events": total,
        "by_status": {str(s): c for s, c in by_status if s},
        "bounce_rate": round(bounce_rate, 2),
        "reply_rate": round(reply_rate, 2)
    }
