"""OutreachDraft model — stores email drafts for preview & approve workflow."""
from datetime import datetime
from enum import Enum as PyEnum
from sqlalchemy import (
    Column, Integer, String, DateTime, Enum, Text, Boolean,
    ForeignKey, Float,
)
from app.db.base import Base


class DraftStatus(str, PyEnum):
    """Draft lifecycle status."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    SENT = "sent"
    EXPIRED = "expired"


class DraftSource(str, PyEnum):
    """Where the draft originated."""
    CAMPAIGN = "campaign"
    PIPELINE = "pipeline"
    BROADCAST = "broadcast"


class OutreachDraft(Base):
    """An email draft awaiting review before sending."""

    __tablename__ = "outreach_drafts"

    draft_id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    contact_id = Column(Integer, ForeignKey("contact_details.contact_id"), nullable=False, index=True)
    lead_id = Column(Integer, ForeignKey("lead_details.lead_id"), nullable=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.campaign_id"), nullable=True, index=True)
    step_id = Column(Integer, ForeignKey("sequence_steps.step_id"), nullable=True)
    mailbox_id = Column(Integer, ForeignKey("sender_mailboxes.mailbox_id"), nullable=False)

    # Email content (post-rewrite)
    subject = Column(String(500), nullable=False)
    body_html = Column(Text, nullable=False)
    body_text = Column(Text, nullable=True)

    # Original content (pre-AI-rewrite)
    original_subject = Column(String(500), nullable=True)
    original_body_html = Column(Text, nullable=True)

    # Status
    status = Column(
        Enum(DraftStatus, values_callable=lambda x: [e.value for e in x]),
        default=DraftStatus.PENDING,
        nullable=False,
        index=True,
    )
    source = Column(
        Enum(DraftSource, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )

    # Spam / deliverability
    spam_score = Column(Integer, default=0, nullable=False)
    spam_grade = Column(String(20), default="clean", nullable=False)
    flagged_words_json = Column(Text, nullable=True)
    deliverability_score = Column(Float, nullable=True)

    # AI rewrite flag
    ai_rewritten = Column(Boolean, default=False, nullable=False)

    # Approval tracking
    approved_by = Column(Integer, ForeignKey("users.user_id"), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    rejected_by = Column(Integer, ForeignKey("users.user_id"), nullable=True)
    rejected_at = Column(DateTime, nullable=True)
    sent_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)

    # Batch grouping
    batch_id = Column(String(36), nullable=True, index=True)

    # A/B variant tracking
    variant_index = Column(Integer, nullable=True)

    def __repr__(self) -> str:
        return f"<OutreachDraft(draft_id={self.draft_id}, status='{self.status}', contact_id={self.contact_id})>"
