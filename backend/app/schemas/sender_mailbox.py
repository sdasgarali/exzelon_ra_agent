"""Pydantic schemas for sender mailbox management."""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, EmailStr, Field
from enum import Enum


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
    provider: EmailProviderEnum = EmailProviderEnum.MICROSOFT_365
    smtp_host: Optional[str] = None
    smtp_port: int = 587
    imap_host: Optional[str] = None
    imap_port: int = 993
    daily_send_limit: int = 30
    notes: Optional[str] = None
    email_signature_json: Optional[str] = None


class SenderMailboxCreate(SenderMailboxBase):
    """Schema for creating a sender mailbox."""
    password: Optional[str] = None  # Optional for OAuth2 mailboxes
    auth_method: str = "password"  # "password" | "oauth2"
    oauth_tenant_id: Optional[str] = None
    warmup_status: WarmupStatusEnum = WarmupStatusEnum.INACTIVE
    is_active: bool = True


class SenderMailboxUpdate(BaseModel):
    """Schema for updating a sender mailbox."""
    email: Optional[EmailStr] = None
    display_name: Optional[str] = None
    password: Optional[str] = None
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


class SenderMailboxResponse(SenderMailboxBase):
    """Schema for mailbox response (excludes password)."""
    mailbox_id: int
    warmup_status: WarmupStatusEnum
    is_active: bool
    emails_sent_today: int
    total_emails_sent: int
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
