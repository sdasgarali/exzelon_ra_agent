"""Inbox message model for unified inbox (Unibox)."""
from datetime import datetime
from enum import Enum as PyEnum
from sqlalchemy import (
    Column, Integer, String, DateTime, Enum, Text, Boolean,
    ForeignKey, Index,
)
from app.db.base import Base


class MessageDirection(str, PyEnum):
    """Email direction."""
    SENT = "sent"
    RECEIVED = "received"


class InboxMessage(Base):
    """Unified inbox message — both sent outreach and received replies."""

    __tablename__ = "inbox_messages"

    message_id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.tenant_id"), nullable=False, index=True)

    # Thread grouping
    thread_id = Column(String(100), nullable=False, index=True)

    # Relationships
    contact_id = Column(Integer, ForeignKey("contact_details.contact_id"), nullable=True)
    mailbox_id = Column(Integer, ForeignKey("sender_mailboxes.mailbox_id"), nullable=True)
    outreach_event_id = Column(Integer, ForeignKey("outreach_events.event_id"), nullable=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.campaign_id"), nullable=True)

    # Direction
    direction = Column(
        Enum(MessageDirection, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )

    # Email headers
    from_email = Column(String(255), nullable=False)
    to_email = Column(String(255), nullable=False)
    subject = Column(String(500), nullable=True)
    body_html = Column(Text, nullable=True)
    body_text = Column(Text, nullable=True)
    raw_message_id = Column(String(255), nullable=True)  # Message-ID header
    in_reply_to = Column(String(255), nullable=True)

    # Timestamps
    received_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Status
    is_read = Column(Boolean, default=False, nullable=False)

    # Categorization
    category = Column(String(50), nullable=True)  # interested/not_interested/ooo/question/referral/do_not_contact/other
    sentiment = Column(String(20), nullable=True)  # positive/negative/neutral

    # Soft delete
    is_deleted = Column(Boolean, default=False, nullable=False)
    deleted_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("idx_inbox_tenant", "tenant_id"),
        Index("idx_inbox_thread", "thread_id"),
        Index("idx_inbox_contact", "contact_id"),
        Index("idx_inbox_mailbox", "mailbox_id"),
        Index("idx_inbox_received", "received_at"),
        Index("idx_inbox_read", "is_read"),
        Index("idx_inbox_category", "category"),
    )

    def __repr__(self) -> str:
        return f"<InboxMessage(message_id={self.message_id}, thread='{self.thread_id}', dir='{self.direction}')>"
