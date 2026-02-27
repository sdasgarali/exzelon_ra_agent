"""Sender mailbox management endpoints."""
import smtplib
import imaplib
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.api.deps import get_db, require_role
from app.db.models.user import User, UserRole
from app.db.models.sender_mailbox import SenderMailbox, WarmupStatus, EmailProvider
from app.schemas.sender_mailbox import (
    SenderMailboxCreate,
    SenderMailboxUpdate,
    SenderMailboxResponse,
    SenderMailboxListResponse,
    SenderMailboxStatsResponse,
    TestMailboxConnectionRequest,
    TestMailboxConnectionResponse,
    WarmupStatusEnum
)

router = APIRouter(prefix="/mailboxes", tags=["Mailboxes"])


def mailbox_to_response(mailbox: SenderMailbox) -> SenderMailboxResponse:
    """Convert mailbox model to response schema."""
    return SenderMailboxResponse(
        mailbox_id=mailbox.mailbox_id,
        email=mailbox.email,
        display_name=mailbox.display_name,
        provider=mailbox.provider.value if mailbox.provider else "microsoft_365",
        smtp_host=mailbox.smtp_host,
        smtp_port=mailbox.smtp_port,
        imap_host=mailbox.imap_host,
        imap_port=mailbox.imap_port,
        warmup_status=mailbox.warmup_status.value if mailbox.warmup_status else "inactive",
        is_active=mailbox.is_active,
        daily_send_limit=mailbox.daily_send_limit,
        emails_sent_today=mailbox.emails_sent_today,
        total_emails_sent=mailbox.total_emails_sent,
        last_sent_at=mailbox.last_sent_at,
        bounce_count=mailbox.bounce_count,
        reply_count=mailbox.reply_count,
        complaint_count=mailbox.complaint_count,
        warmup_started_at=mailbox.warmup_started_at,
        warmup_completed_at=mailbox.warmup_completed_at,
        warmup_days_completed=mailbox.warmup_days_completed,
        notes=mailbox.notes,
        created_at=mailbox.created_at,
        updated_at=mailbox.updated_at,
        connection_status=mailbox.connection_status or "untested",
        last_connection_test_at=mailbox.last_connection_test_at,
        connection_error=mailbox.connection_error,
        can_send=mailbox.can_send,
        remaining_daily_quota=mailbox.remaining_daily_quota,
        email_signature_json=mailbox.email_signature_json,
        is_archived=mailbox.is_archived
    )


@router.get("", response_model=SenderMailboxListResponse)
async def list_mailboxes(
    status: Optional[str] = Query(None, description="Filter by warmup status"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    provider: Optional[str] = Query(None, description="Filter by provider"),
    show_archived: bool = Query(False, description="Include archived mailboxes"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR]))
):
    """List all sender mailboxes."""
    query = db.query(SenderMailbox)

    if show_archived:
        query = query.filter(SenderMailbox.is_archived == True)
    else:
        query = query.filter(SenderMailbox.is_archived == False)

    if status:
        try:
            warmup_status = WarmupStatus(status)
            query = query.filter(SenderMailbox.warmup_status == warmup_status)
        except ValueError:
            pass

    if is_active is not None:
        query = query.filter(SenderMailbox.is_active == is_active)

    if provider:
        try:
            email_provider = EmailProvider(provider)
            query = query.filter(SenderMailbox.provider == email_provider)
        except ValueError:
            pass

    mailboxes = query.order_by(SenderMailbox.email).all()

    # Calculate counts
    active_count = sum(1 for m in mailboxes if m.is_active)
    ready_count = sum(1 for m in mailboxes if m.warmup_status == WarmupStatus.COLD_READY and m.is_active)

    return SenderMailboxListResponse(
        items=[mailbox_to_response(m) for m in mailboxes],
        total=len(mailboxes),
        active_count=active_count,
        ready_count=ready_count
    )


@router.get("/stats", response_model=SenderMailboxStatsResponse)
async def get_mailbox_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR]))
):
    """Get mailbox statistics."""
    mailboxes = db.query(SenderMailbox).all()

    total = len(mailboxes)
    active = sum(1 for m in mailboxes if m.is_active)
    cold_ready = sum(1 for m in mailboxes if m.warmup_status == WarmupStatus.COLD_READY and m.is_active)
    warming_up = sum(1 for m in mailboxes if m.warmup_status == WarmupStatus.WARMING_UP)
    paused = sum(1 for m in mailboxes if m.warmup_status == WarmupStatus.PAUSED)

    # Calculate daily capacity for active, ready mailboxes
    ready_mailboxes = [m for m in mailboxes if m.warmup_status in [WarmupStatus.COLD_READY, WarmupStatus.ACTIVE] and m.is_active]
    total_daily_capacity = sum(m.daily_send_limit for m in ready_mailboxes)
    used_today = sum(m.emails_sent_today for m in ready_mailboxes)

    # Total metrics
    total_emails_sent = sum(m.total_emails_sent for m in mailboxes)
    total_bounces = sum(m.bounce_count for m in mailboxes)
    total_replies = sum(m.reply_count for m in mailboxes)

    return SenderMailboxStatsResponse(
        total_mailboxes=total,
        active_mailboxes=active,
        cold_ready_mailboxes=cold_ready,
        warming_up_mailboxes=warming_up,
        paused_mailboxes=paused,
        total_daily_capacity=total_daily_capacity,
        used_today=used_today,
        available_today=total_daily_capacity - used_today,
        total_emails_sent=total_emails_sent,
        total_bounces=total_bounces,
        total_replies=total_replies
    )


@router.get("/{mailbox_id}", response_model=SenderMailboxResponse)
async def get_mailbox(
    mailbox_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR]))
):
    """Get a specific mailbox by ID."""
    mailbox = db.query(SenderMailbox).filter(SenderMailbox.mailbox_id == mailbox_id).first()
    if not mailbox:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mailbox not found"
        )
    return mailbox_to_response(mailbox)


@router.post("", response_model=SenderMailboxResponse)
async def create_mailbox(
    mailbox_in: SenderMailboxCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN]))
):
    """Create a new sender mailbox (Admin only)."""
    # Check if email already exists
    existing = db.query(SenderMailbox).filter(SenderMailbox.email == mailbox_in.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Mailbox with email {mailbox_in.email} already exists"
        )

    # Set default SMTP/IMAP hosts based on provider
    smtp_host = mailbox_in.smtp_host
    imap_host = mailbox_in.imap_host

    if mailbox_in.provider == "microsoft_365" and not smtp_host:
        smtp_host = "smtp.office365.com"
        imap_host = "outlook.office365.com"
    elif mailbox_in.provider == "gmail" and not smtp_host:
        smtp_host = "smtp.gmail.com"
        imap_host = "imap.gmail.com"

    mailbox = SenderMailbox(
        email=mailbox_in.email,
        display_name=mailbox_in.display_name,
        password=mailbox_in.password,  # In production, encrypt this
        provider=EmailProvider(mailbox_in.provider),
        smtp_host=smtp_host,
        smtp_port=mailbox_in.smtp_port,
        imap_host=imap_host,
        imap_port=mailbox_in.imap_port,
        warmup_status=WarmupStatus(mailbox_in.warmup_status),
        is_active=mailbox_in.is_active,
        daily_send_limit=mailbox_in.daily_send_limit,
        notes=mailbox_in.notes
    )

    db.add(mailbox)
    db.commit()
    db.refresh(mailbox)

    # Auto-assess warmup status for new mailbox
    try:
        from app.services.pipelines.warmup_engine import run_warmup_assessment
        run_warmup_assessment(
            triggered_by=current_user.email,
            mailbox_id=mailbox.mailbox_id
        )
        db.refresh(mailbox)
    except Exception:
        pass  # Non-critical: warmup assessment failure should not block creation

    return mailbox_to_response(mailbox)


@router.put("/{mailbox_id}", response_model=SenderMailboxResponse)
async def update_mailbox(
    mailbox_id: int,
    mailbox_in: SenderMailboxUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN]))
):
    """Update a sender mailbox (Admin only)."""
    mailbox = db.query(SenderMailbox).filter(SenderMailbox.mailbox_id == mailbox_id).first()
    if not mailbox:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mailbox not found"
        )

    # Update fields if provided
    update_data = mailbox_in.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        if field == "warmup_status" and value:
            setattr(mailbox, field, WarmupStatus(value))
        elif field == "provider" and value:
            setattr(mailbox, field, EmailProvider(value))
        else:
            setattr(mailbox, field, value)

    db.commit()
    db.refresh(mailbox)

    return mailbox_to_response(mailbox)


@router.delete("/{mailbox_id}")
async def delete_mailbox(
    mailbox_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN]))
):
    """Archive a sender mailbox (soft delete, Admin only)."""
    mailbox = db.query(SenderMailbox).filter(SenderMailbox.mailbox_id == mailbox_id).first()
    if not mailbox:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mailbox not found"
        )

    # Soft delete: archive and deactivate instead of hard deleting
    mailbox.is_archived = True
    mailbox.is_active = False
    db.commit()

    return {"message": f"Mailbox {mailbox.email} archived successfully"}


@router.post("/{mailbox_id}/test-connection", response_model=TestMailboxConnectionResponse)
async def test_mailbox_connection(
    mailbox_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR]))
):
    """Test connection for an existing mailbox."""
    mailbox = db.query(SenderMailbox).filter(SenderMailbox.mailbox_id == mailbox_id).first()
    if not mailbox:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mailbox not found"
        )

    smtp_connected = False
    imap_connected = False
    messages = []

    # Test SMTP connection
    try:
        smtp_host = mailbox.smtp_host or "smtp.office365.com"
        server = smtplib.SMTP(smtp_host, mailbox.smtp_port, timeout=10)
        server.starttls()
        server.login(mailbox.email, mailbox.password)
        server.quit()
        smtp_connected = True
        messages.append("SMTP connection successful")
    except smtplib.SMTPAuthenticationError:
        messages.append("SMTP authentication failed - check credentials")
    except smtplib.SMTPConnectError:
        messages.append(f"Could not connect to SMTP server {mailbox.smtp_host}")
    except Exception as e:
        messages.append(f"SMTP error: {str(e)}")

    # Test IMAP connection (optional)
    if mailbox.imap_host:
        try:
            imap = imaplib.IMAP4_SSL(mailbox.imap_host, mailbox.imap_port)
            imap.login(mailbox.email, mailbox.password)
            imap.logout()
            imap_connected = True
            messages.append("IMAP connection successful")
        except Exception as e:
            messages.append(f"IMAP error: {str(e)}")

    success = smtp_connected  # SMTP is required, IMAP is optional

    # Track connection status and error message for warmup engine filtering
    if success:
        mailbox.connection_status = "successful"
        mailbox.connection_error = None
    else:
        mailbox.connection_status = "failed"
        mailbox.connection_error = " | ".join(messages)
    mailbox.last_connection_test_at = datetime.utcnow()
    db.commit()

    return TestMailboxConnectionResponse(
        success=success,
        message=" | ".join(messages),
        smtp_connected=smtp_connected,
        imap_connected=imap_connected
    )


@router.post("/test-connection", response_model=TestMailboxConnectionResponse)
async def test_new_mailbox_connection(
    request: TestMailboxConnectionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR]))
):
    """Test connection for new mailbox credentials (before saving)."""
    if request.mailbox_id:
        # Test existing mailbox
        return await test_mailbox_connection(request.mailbox_id, db, current_user)

    if not request.email or not request.password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email and password required for connection test"
        )

    smtp_connected = False
    messages = []

    # Determine SMTP host
    smtp_host = request.smtp_host
    if not smtp_host:
        if request.provider == "microsoft_365":
            smtp_host = "smtp.office365.com"
        elif request.provider == "gmail":
            smtp_host = "smtp.gmail.com"
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="SMTP host required for custom provider"
            )

    # Test SMTP connection
    try:
        server = smtplib.SMTP(smtp_host, request.smtp_port, timeout=10)
        server.starttls()
        server.login(request.email, request.password)
        server.quit()
        smtp_connected = True
        messages.append("SMTP connection successful")
    except smtplib.SMTPAuthenticationError:
        messages.append("SMTP authentication failed - check credentials")
    except smtplib.SMTPConnectError:
        messages.append(f"Could not connect to SMTP server {smtp_host}")
    except Exception as e:
        messages.append(f"SMTP error: {str(e)}")

    return TestMailboxConnectionResponse(
        success=smtp_connected,
        message=" | ".join(messages),
        smtp_connected=smtp_connected,
        imap_connected=False
    )


@router.post("/{mailbox_id}/update-status")
async def update_mailbox_status(
    mailbox_id: int,
    new_status: WarmupStatusEnum,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN]))
):
    """Update warmup status of a mailbox (Admin only)."""
    mailbox = db.query(SenderMailbox).filter(SenderMailbox.mailbox_id == mailbox_id).first()
    if not mailbox:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mailbox not found"
        )

    from datetime import datetime

    old_status = mailbox.warmup_status
    mailbox.warmup_status = WarmupStatus(new_status)

    # Track warmup completion
    if new_status == WarmupStatusEnum.COLD_READY and old_status == WarmupStatus.WARMING_UP:
        mailbox.warmup_completed_at = datetime.utcnow()
    elif new_status == WarmupStatusEnum.WARMING_UP and old_status != WarmupStatus.WARMING_UP:
        mailbox.warmup_started_at = datetime.utcnow()
        mailbox.warmup_days_completed = 0

    db.commit()
    db.refresh(mailbox)

    return {
        "message": f"Mailbox status updated from {old_status.value} to {new_status}",
        "mailbox": mailbox_to_response(mailbox)
    }


@router.post("/reset-daily-counts")
async def reset_daily_counts(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN]))
):
    """Reset daily email counts for all mailboxes (Admin only).
    This should be called by a scheduled job at midnight."""
    count = db.query(SenderMailbox).update({SenderMailbox.emails_sent_today: 0})
    db.commit()

    return {"message": f"Reset daily counts for {count} mailboxes"}


@router.get("/available/for-sending", response_model=List[SenderMailboxResponse])
async def get_available_mailboxes_for_sending(
    count: int = Query(1, ge=1, le=10, description="Number of mailboxes needed"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR]))
):
    """Get available mailboxes for sending (cold-ready with remaining quota)."""
    mailboxes = db.query(SenderMailbox).filter(
        SenderMailbox.is_active == True,
        SenderMailbox.warmup_status.in_([WarmupStatus.COLD_READY, WarmupStatus.ACTIVE]),
        SenderMailbox.emails_sent_today < SenderMailbox.daily_send_limit
    ).order_by(
        SenderMailbox.emails_sent_today.asc()  # Prefer mailboxes with lower usage
    ).limit(count).all()

    return [mailbox_to_response(m) for m in mailboxes]
