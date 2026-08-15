"""Pydantic schemas for sender mailbox management."""
import re
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, EmailStr, field_validator
from enum import Enum


def normalize_us_phone(value: Optional[str]) -> Optional[str]:
    """Normalize a US phone number to "(NNN) NNN-NNNN".

    Accepts common inputs (digits, dashes, dots, spaces, parens, optional +1
    country code). Blank/None is allowed (returns None) — the UI enforces that
    the field is provided; the API stays lenient so imports/bulk-add don't break.
    Raises ValueError for a non-blank value that isn't a valid US number.
    """
    if value is None:
        return None
    raw = value.strip()
    if not raw:
        return None
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) != 10:
        raise ValueError("Phone must be a valid US number, e.g. (555) 123-4567")
    return f"({digits[0:3]}) {digits[3:6]}-{digits[6:10]}"


class WarmupStatusEnum(str, Enum):
    """Mailbox warmup status."""
    WARMING_UP = "warming_up"
    COLD_READY = "cold_ready"
    ACTIVE = "active"
    PAUSED = "paused"
    INACTIVE = "inactive"
    BLACKLISTED = "blacklisted"


class EmailProviderEnum(str, Enum):
    """Email service provider."""
    MICROSOFT_365 = "microsoft_365"
    GMAIL = "gmail"
    SMTP = "smtp"
    OTHER = "other"


class SenderMailboxBase(BaseModel):
    """Base schema for sender mailbox."""
    email: EmailStr
    display_name: Optional[str] = None
    sender_first_name: Optional[str] = None
    sender_last_name: Optional[str] = None
    phone: Optional[str] = None
    linkedin_url: Optional[str] = None
    provider: EmailProviderEnum = EmailProviderEnum.MICROSOFT_365

    _normalize_phone = field_validator("phone")(lambda cls, v: normalize_us_phone(v))
    smtp_host: Optional[str] = None
    smtp_port: int = 587
    imap_host: Optional[str] = None
    imap_port: int = 993
    daily_send_limit: int = 30
    notes: Optional[str] = None
    email_signature_json: Optional[str] = None


class SenderMailboxCreate(SenderMailboxBase):
    """Schema for creating a sender mailbox."""
    password: Optional[str] = None  # Optional for OAuth2 mailboxes (this is the SEND credential)
    auth_method: str = "password"  # "password" | "oauth2"
    oauth_tenant_id: Optional[str] = None
    warmup_status: WarmupStatusEnum = WarmupStatusEnum.INACTIVE
    is_active: bool = True
    outreach_role_id: Optional[int] = None
    # For personal (non-auto_outbound) mailboxes: the SYSTEM LOGIN password used to
    # create/link a User so this person can sign in. Ignored for RA/machine mailboxes.
    login_password: Optional[str] = None
    # Link to an existing user instead of creating one (used by "add my email as mailbox").
    user_id: Optional[int] = None


class SenderMailboxUpdate(BaseModel):
    """Schema for updating a sender mailbox."""
    email: Optional[EmailStr] = None
    display_name: Optional[str] = None
    sender_first_name: Optional[str] = None
    sender_last_name: Optional[str] = None
    phone: Optional[str] = None
    linkedin_url: Optional[str] = None
    password: Optional[str] = None

    _normalize_phone = field_validator("phone")(lambda cls, v: normalize_us_phone(v))
    auth_method: Optional[str] = None
    oauth_tenant_id: Optional[str] = None
    provider: Optional[EmailProviderEnum] = None
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    imap_host: Optional[str] = None
    imap_port: Optional[int] = None
    warmup_status: Optional[WarmupStatusEnum] = None
    is_active: Optional[bool] = None
    daily_send_limit: Optional[int] = None
    notes: Optional[str] = None
    email_signature_json: Optional[str] = None
    outreach_role_id: Optional[int] = None


class SenderMailboxResponse(SenderMailboxBase):
    """Schema for mailbox response (excludes password)."""
    mailbox_id: int
    warmup_status: WarmupStatusEnum
    is_active: bool
    emails_sent_today: int
    total_emails_sent: int
    warmup_emails_sent: int = 0
    outreach_emails_sent: int = 0
    last_sent_at: Optional[datetime] = None
    bounce_count: int
    reply_count: int
    complaint_count: int
    warmup_started_at: Optional[datetime] = None
    warmup_completed_at: Optional[datetime] = None
    warmup_days_completed: int
    created_at: datetime
    updated_at: datetime

    connection_status: str = "untested"
    last_connection_test_at: Optional[datetime] = None
    connection_error: Optional[str] = None
    email_signature_json: Optional[str] = None

    is_archived: bool = False

    # OAuth fields
    auth_method: str = "password"
    oauth_tenant_id: Optional[str] = None
    oauth_connected: bool = False  # True if OAuth tokens are stored

    # Outreach role
    outreach_role_id: Optional[int] = None
    outreach_role_name: Optional[str] = None

    # Linked login user (personal mailboxes only)
    user_id: Optional[int] = None
    linked_login_email: Optional[str] = None

    # Computed fields
    can_send: bool = False
    remaining_daily_quota: int = 0

    class Config:
        from_attributes = True


class SenderMailboxListResponse(BaseModel):
    """Schema for listing mailboxes."""
    items: List[SenderMailboxResponse]
    total: int
    active_count: int
    ready_count: int  # Cold-ready mailboxes


class SenderMailboxStatsResponse(BaseModel):
    """Schema for mailbox statistics."""
    total_mailboxes: int
    active_mailboxes: int
    cold_ready_mailboxes: int
    warming_up_mailboxes: int
    paused_mailboxes: int
    total_daily_capacity: int
    used_today: int
    available_today: int
    total_emails_sent: int
    total_bounces: int
    total_replies: int
    role_counts: dict = {}


class TestMailboxConnectionRequest(BaseModel):
    """Schema for testing mailbox connection."""
    mailbox_id: Optional[int] = None
    email: Optional[EmailStr] = None
    password: Optional[str] = None
    provider: EmailProviderEnum = EmailProviderEnum.MICROSOFT_365
    smtp_host: Optional[str] = None
    smtp_port: int = 587


class TestMailboxConnectionResponse(BaseModel):
    """Schema for mailbox connection test result."""
    success: bool
    message: str
    smtp_connected: bool = False
    imap_connected: bool = False
