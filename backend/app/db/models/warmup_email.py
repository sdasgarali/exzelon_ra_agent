"""WarmupEmail model - tracks every warmup email sent between peer mailboxes."""
import uuid
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, Enum
from sqlalchemy.sql import func
import enum

from app.db.base import Base


class WarmupEmailStatus(str, enum.Enum):
    SENT = 'sent'
    DELIVERED = 'delivered'
    OPENED = 'opened'
    REPLIED = 'replied'
    BOUNCED = 'bounced'
    FAILED = 'failed'


class WarmupEmail(Base):
    """Tracks every warmup email sent between peer mailboxes."""

    __tablename__ = 'warmup_emails'

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.tenant_id"), nullable=True, index=True)
    sender_mailbox_id = Column(Integer, ForeignKey('sender_mailboxes.mailbox_id'), nullable=False, index=True)
    receiver_mailbox_id = Column(Integer, ForeignKey('sender_mailboxes.mailbox_id'), nullable=True, index=True)
    subject = Column(String(500), nullable=True)
    body_html = Column(Text, nullable=True)
    body_text = Column(Text, nullable=True)
    message_id = Column(String(255), nullable=True)
    sent_at = Column(DateTime, server_default=func.now())
    opened_at = Column(DateTime, nullable=True)
    replied_at = Column(DateTime, nullable=True)
    status = Column(Enum(WarmupEmailStatus, values_callable=lambda x: [e.value for e in x]), default=WarmupEmailStatus.SENT)
    tracking_id = Column(String(64), default=lambda: str(uuid.uuid4()), unique=True, index=True)
    ai_generated = Column(Boolean, default=False)
    ai_provider = Column(String(50), nullable=True)
