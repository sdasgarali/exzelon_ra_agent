"""Sender mailbox model for managing email sending accounts."""
from sqlalchemy import Column, Integer, String, Enum, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.sql import func
import enum

from app.db.base import Base


class WarmupStatus(str, enum.Enum):
    """Mailbox warmup status."""
    WARMING_UP = "warming_up"
    COLD_READY = "cold_ready"
    ACTIVE = "active"
    PAUSED = "paused"
    INACTIVE = "inactive"
    BLACKLISTED = "blacklisted"
    RECOVERING = "recovering"


class EmailProvider(str, enum.Enum):
    """Email service provider."""
    MICROSOFT_365 = "microsoft_365"
    GMAIL = "gmail"
    SMTP = "smtp"
    OTHER = "other"


class SenderMailbox(Base):
    """Model for sender email accounts used in outreach."""

    __tablename__ = "sender_mailboxes"

    mailbox_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.tenant_id"), nullable=True, index=True)

    # Email account details
    email = Column(String(255), unique=True, nullable=False, index=True)
    display_name = Column(String(255), nullable=True)

    # Authentication
    password = Column(String(500), nullable=False)

    # Provider configuration
    provider = Column(Enum(EmailProvider, values_callable=lambda x: [e.value for e in x]), default=EmailProvider.MICROSOFT_365)
    smtp_host = Column(String(255), nullable=True)
    smtp_port = Column(Integer, default=587)
    imap_host = Column(String(255), nullable=True)
    imap_port = Column(Integer, default=993)

    # Status tracking
    warmup_status = Column(Enum(WarmupStatus, values_callable=lambda x: [e.value for e in x]), default=WarmupStatus.INACTIVE)
    is_active = Column(Boolean, default=True)

    # Usage tracking
    daily_send_limit = Column(Integer, default=30)
    emails_sent_today = Column(Integer, default=0)
    total_emails_sent = Column(Integer, default=0)
    last_sent_at = Column(DateTime, nullable=True)

    # Deliverability metrics
    bounce_count = Column(Integer, default=0)
    reply_count = Column(Integer, default=0)
    complaint_count = Column(Integer, default=0)

    # Warmup tracking
    warmup_started_at = Column(DateTime, nullable=True)
    warmup_completed_at = Column(DateTime, nullable=True)
    warmup_days_completed = Column(Integer, default=0)

    # Notes and metadata
    notes = Column(Text, nullable=True)
    email_signature_json = Column(Text, nullable=True)  # JSON: {sender_name, title, phone, email, company, website}

    # Timestamps
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # === Enterprise warmup fields ===
    warmup_profile_id = Column(Integer, nullable=True)
    connection_status = Column(String(20), default="untested")
    last_connection_test_at = Column(DateTime, nullable=True)
    warmup_emails_sent = Column(Integer, default=0)
    warmup_emails_received = Column(Integer, default=0)
    warmup_opens = Column(Integer, default=0)
    warmup_replies = Column(Integer, default=0)
    last_dns_check_at = Column(DateTime, nullable=True)
    last_blacklist_check_at = Column(DateTime, nullable=True)
    dns_score = Column(Integer, default=0)
    is_blacklisted = Column(Boolean, default=False)
    auto_recovery_started_at = Column(DateTime, nullable=True)
    connection_error = Column(Text, nullable=True)

    def __repr__(self):
        return f"<SenderMailbox {self.email} ({self.warmup_status.value})>"

    @property
    def can_send(self) -> bool:
        """Check if mailbox can send emails."""
        return (
            self.is_active and
            self.warmup_status in [WarmupStatus.COLD_READY, WarmupStatus.ACTIVE] and
            self.emails_sent_today < self.daily_send_limit
        )

    @property
    def remaining_daily_quota(self) -> int:
        """Get remaining emails that can be sent today."""
        return max(0, self.daily_send_limit - self.emails_sent_today)
