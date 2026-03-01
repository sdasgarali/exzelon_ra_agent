"""Outreach events model for tracking sends."""
import uuid
from datetime import datetime
from enum import Enum as PyEnum
from sqlalchemy import Column, Integer, String, DateTime, Enum, Text, ForeignKey, Index
from app.db.base import Base


class OutreachStatus(str, PyEnum):
    """Outreach event status."""
    SENT = "sent"
    REPLIED = "replied"
    BOUNCED = "bounced"
    SKIPPED = "skipped"


class OutreachChannel(str, PyEnum):
    """Outreach channel type."""
    MAILMERGE = "mailmerge"
    SMTP = "smtp"
    M365 = "m365"
    GMAIL = "gmail"
    API = "api"


class OutreachEvent(Base):
    """Outreach events model - Every send attempt and result."""

    __tablename__ = "outreach_events"

    event_id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.tenant_id"), nullable=True, index=True)
    contact_id = Column(Integer, ForeignKey('contact_details.contact_id'), nullable=False)
    lead_id = Column(Integer, ForeignKey('lead_details.lead_id'), nullable=True)
    sender_mailbox_id = Column(Integer, ForeignKey('sender_mailboxes.mailbox_id'), nullable=True)
    sent_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    channel = Column(Enum(OutreachChannel, values_callable=lambda x: [e.value for e in x]), nullable=False)
    template_id = Column(Integer, nullable=True)
    subject = Column(String(500), nullable=True)
    message_id = Column(String(255), nullable=True)
    status = Column(Enum(OutreachStatus, values_callable=lambda x: [e.value for e in x]), nullable=False)
    bounce_reason = Column(Text, nullable=True)
    reply_detected_at = Column(DateTime, nullable=True)
    skip_reason = Column(Text, nullable=True)

    # Email body storage
    body_html = Column(Text, nullable=True)
    body_text = Column(Text, nullable=True)

    # Unsubscribe tracking
    tracking_id = Column(String(64), default=lambda: str(uuid.uuid4()), unique=True, index=True, nullable=True)

    # Reply content storage
    reply_subject = Column(String(500), nullable=True)
    reply_body = Column(Text, nullable=True)

    __table_args__ = (
        Index('idx_outreach_contact', 'contact_id'),
        Index('idx_outreach_lead', 'lead_id'),
        Index('idx_outreach_status', 'status'),
        Index('idx_outreach_sent_at', 'sent_at'),
        Index('idx_outreach_message_id', 'message_id'),
        Index('idx_outreach_sender_mailbox', 'sender_mailbox_id'),
    )

    def __repr__(self) -> str:
        return f"<OutreachEvent(event_id={self.event_id}, contact_id={self.contact_id}, status='{self.status}')>"
