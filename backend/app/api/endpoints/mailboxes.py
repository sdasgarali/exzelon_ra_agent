"""Sender mailbox management endpoints."""
import asyncio
import smtplib
import imaplib
import socket
import ssl
import structlog
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.api.deps import get_db, require_role
from app.db.models.user import User, UserRole
from app.db.models.sender_mailbox import SenderMailbox, WarmupStatus, EmailProvider
from app.core.encryption import encrypt_field, decrypt_field, is_encrypted

logger = structlog.get_logger()
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


# ---- OAuth2 endpoints (placed BEFORE /{mailbox_id} routes) ----

@router.get("/oauth/initiate")
async def oauth_initiate(
    mailbox_id: Optional[int] = Query(None, description="Existing mailbox ID to connect OAuth"),
    email: Optional[str] = Query(None, description="Email address for new mailbox OAuth"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN]))
):
    """Initiate Microsoft OAuth2 authorization flow.

    Returns the authorization URL to redirect the user to Microsoft login.
    """
    from app.core.config import settings as app_settings
    if not app_settings.MS365_OAUTH_CLIENT_ID:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MS365 OAuth not configured — set MS365_OAUTH_CLIENT_ID in .env"
        )

    # Determine email and tenant
    target_email = email
    tenant_id = None
    if mailbox_id:
        mailbox = db.query(SenderMailbox).filter(SenderMailbox.mailbox_id == mailbox_id).first()
        if not mailbox:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mailbox not found")
        target_email = mailbox.email
        tenant_id = mailbox.oauth_tenant_id

    if not target_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either mailbox_id or email is required"
        )

    # Build state: encode mailbox_id or email for the callback
    import json as _json, base64 as _b64
    state_data = {"mailbox_id": mailbox_id, "email": target_email, "user_id": current_user.user_id}
    state = _b64.urlsafe_b64encode(_json.dumps(state_data).encode()).decode()

    from app.services.oauth_helper import get_oauth_authorization_url
    auth_url = get_oauth_authorization_url(
        email=target_email,
        tenant_id=tenant_id,
        state=state,
    )

    return {"authorization_url": auth_url}


@router.post("/oauth/callback")
async def oauth_callback(
    request_body: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN]))
):
    """Handle OAuth2 callback — exchange authorization code for tokens.

    Body: { "code": "...", "state": "..." }
    """
    code = request_body.get("code")
    state = request_body.get("state")
    if not code or not state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Both 'code' and 'state' are required"
        )

    # Decode state
    import json as _json, base64 as _b64
    try:
        state_data = _json.loads(_b64.urlsafe_b64decode(state).decode())
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid state parameter")

    mailbox_id = state_data.get("mailbox_id")
    target_email = state_data.get("email")

    # Find or validate the mailbox
    if mailbox_id:
        mailbox = db.query(SenderMailbox).filter(SenderMailbox.mailbox_id == mailbox_id).first()
        if not mailbox:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mailbox not found")
    else:
        # For new mailbox flow — find by email
        mailbox = db.query(SenderMailbox).filter(SenderMailbox.email == target_email).first()
        if not mailbox:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Mailbox not found — create the mailbox first, then connect OAuth"
            )

    # Exchange code for tokens
    from app.services.oauth_helper import exchange_code_for_tokens
    from datetime import timedelta
    try:
        token_data = exchange_code_for_tokens(
            code=code,
            tenant_id=mailbox.oauth_tenant_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    # Store encrypted tokens on the mailbox
    mailbox.auth_method = "oauth2"
    mailbox.oauth_access_token = encrypt_field(token_data["access_token"])
    mailbox.oauth_refresh_token = encrypt_field(token_data["refresh_token"])
    mailbox.oauth_token_expires_at = datetime.utcnow() + timedelta(seconds=token_data["expires_in"])
    db.commit()

    logger.info("OAuth2 tokens stored", mailbox_id=mailbox.mailbox_id, email=mailbox.email)

    return {
        "success": True,
        "mailbox_id": mailbox.mailbox_id,
        "message": "OAuth2 connected successfully",
    }


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
        is_archived=mailbox.is_archived,
        auth_method=mailbox.auth_method or "password",
        oauth_tenant_id=mailbox.oauth_tenant_id,
        oauth_connected=bool(mailbox.oauth_refresh_token),
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
        password=encrypt_field(mailbox_in.password) if mailbox_in.password else None,
        auth_method=mailbox_in.auth_method,
        oauth_tenant_id=mailbox_in.oauth_tenant_id,
        provider=EmailProvider(mailbox_in.provider),
        smtp_host=smtp_host,
        smtp_port=mailbox_in.smtp_port,
        imap_host=imap_host,
        imap_port=mailbox_in.imap_port,
        warmup_status=WarmupStatus(mailbox_in.warmup_status),
        is_active=mailbox_in.is_active,
        daily_send_limit=mailbox_in.daily_send_limit,
        notes=mailbox_in.notes,
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
        elif field == "password" and value:
            setattr(mailbox, field, encrypt_field(value))
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


def _test_smtp_sync(smtp_host: str, smtp_port: int, email: str, password: str = None, mailbox=None, db=None) -> tuple[bool, str]:
    """Blocking SMTP test — run via asyncio.to_thread().

    Supports both password-based and OAuth2 (XOAUTH2) authentication.
    """
    try:
        if smtp_port == 465:
            server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=15)
        else:
            server = smtplib.SMTP(smtp_host, smtp_port, timeout=15)
            server.starttls()

        # Use OAuth2 if mailbox is configured for it
        if mailbox and getattr(mailbox, "auth_method", "password") == "oauth2" and db:
            from app.services.oauth_helper import smtp_authenticate
            smtp_authenticate(server, email, mailbox, db)
        else:
            server.login(email, password)

        server.quit()
        return True, "SMTP connection successful"
    except smtplib.SMTPAuthenticationError as e:
        error_str = str(e)
        if "BasicAuthBlocked" in error_str or "5.7.139" in error_str:
            return False, (
                "Microsoft 365 has blocked Basic Authentication for this account. "
                "Use OAuth2 authentication or enable SMTP AUTH in M365 Admin Center "
                "(Users > Active Users > Mail > Manage email apps)."
            )
        return False, "SMTP authentication failed — check email and password (or App Password if MFA is enabled)"
    except smtplib.SMTPConnectError:
        return False, f"Could not connect to SMTP server {smtp_host}:{smtp_port} — check hostname and port"
    except socket.gaierror:
        return False, f"DNS resolution failed for {smtp_host} — check the SMTP hostname"
    except socket.timeout:
        return False, f"Connection to {smtp_host}:{smtp_port} timed out — check firewall or network"
    except ConnectionRefusedError:
        return False, f"Connection refused by {smtp_host}:{smtp_port} — server may be down or port blocked"
    except ssl.SSLError as e:
        return False, f"SSL/TLS error: {e} — try port 587 (STARTTLS) instead of 465 (SSL), or vice versa"
    except ValueError as e:
        # OAuth2-specific errors (token refresh failed, no refresh token, etc.)
        return False, f"OAuth2 error: {str(e)}"
    except Exception as e:
        return False, f"SMTP error: {str(e)}"


def _test_imap_sync(imap_host: str, imap_port: int, email: str, password: str = None, mailbox=None, db=None) -> tuple[bool, str]:
    """Blocking IMAP test — run via asyncio.to_thread().

    Supports both password-based and OAuth2 (XOAUTH2) authentication.
    """
    try:
        imap = imaplib.IMAP4_SSL(imap_host, imap_port, timeout=15)

        if mailbox and getattr(mailbox, "auth_method", "password") == "oauth2" and db:
            from app.services.oauth_helper import imap_authenticate
            imap_authenticate(imap, email, mailbox, db)
        else:
            imap.login(email, password)

        imap.logout()
        return True, "IMAP connection successful"
    except Exception as e:
        error_str = str(e)
        if "BasicAuthBlocked" in error_str:
            return False, (
                "IMAP Basic Auth blocked by M365. "
                "Use OAuth2 authentication or enable IMAP in M365 Admin Center."
            )
        return False, f"IMAP error: {str(e)}"


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

    messages = []
    plain_password = None

    # For password-based auth, decrypt the password
    if getattr(mailbox, "auth_method", "password") != "oauth2":
        try:
            plain_password = decrypt_field(mailbox.password)
            if plain_password and is_encrypted(plain_password):
                logger.error("Password decryption returned encrypted blob", mailbox_id=mailbox_id)
                return TestMailboxConnectionResponse(
                    success=False,
                    message="Password decryption failed — encryption key may have changed. Re-save the mailbox password.",
                    smtp_connected=False,
                    imap_connected=False,
                )
        except RuntimeError as e:
            logger.error("Encryption key error", error=str(e))
            return TestMailboxConnectionResponse(
                success=False,
                message="Server encryption key not configured — contact administrator",
                smtp_connected=False,
                imap_connected=False,
            )
    else:
        # For OAuth2, verify tokens exist
        if not mailbox.oauth_refresh_token:
            return TestMailboxConnectionResponse(
                success=False,
                message="OAuth2 not connected — click 'Connect with Microsoft' first",
                smtp_connected=False,
                imap_connected=False,
            )

    smtp_host = mailbox.smtp_host or "smtp.office365.com"

    # For OAuth2 mailboxes, skip password decryption errors — we use tokens instead
    is_oauth = getattr(mailbox, "auth_method", "password") == "oauth2"

    # Run blocking I/O in thread pool
    smtp_connected, smtp_msg = await asyncio.to_thread(
        _test_smtp_sync, smtp_host, mailbox.smtp_port, mailbox.email,
        plain_password if not is_oauth else None,
        mailbox, db,
    )
    messages.append(smtp_msg)

    imap_connected = False
    if mailbox.imap_host:
        imap_connected, imap_msg = await asyncio.to_thread(
            _test_imap_sync, mailbox.imap_host, mailbox.imap_port, mailbox.email,
            plain_password if not is_oauth else None,
            mailbox, db,
        )
        messages.append(imap_msg)

    success = smtp_connected

    # Track connection status
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
        return await test_mailbox_connection(request.mailbox_id, db, current_user)

    if not request.email or not request.password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email and password required for connection test"
        )

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

    # Run blocking I/O in thread pool
    smtp_connected, smtp_msg = await asyncio.to_thread(
        _test_smtp_sync, smtp_host, request.smtp_port, request.email, request.password
    )

    return TestMailboxConnectionResponse(
        success=smtp_connected,
        message=smtp_msg,
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
