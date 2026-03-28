"""Campaign, SequenceStep, and CampaignContact models for multi-step email sequences."""
from datetime import datetime
from enum import Enum as PyEnum
from sqlalchemy import (
    Column, Integer, String, DateTime, Enum, Text, Boolean,
    ForeignKey, Index, UniqueConstraint,
)
from app.db.base import Base


class CampaignStatus(str, PyEnum):
    """Campaign lifecycle status."""
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class StepType(str, PyEnum):
    """Sequence step type."""
    EMAIL = "email"
    WAIT = "wait"
    CONDITION = "condition"


class CampaignContactStatus(str, PyEnum):
    """Contact enrollment status within a campaign."""
    ACTIVE = "active"
    COMPLETED = "completed"
    REPLIED = "replied"
    BOUNCED = "bounced"
    UNSUBSCRIBED = "unsubscribed"
    PAUSED = "paused"


class Campaign(Base):
    """Campaign model — a named outreach campaign with multi-step sequences."""

    __tablename__ = "campaigns"

    campaign_id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(
        Enum(CampaignStatus, values_callable=lambda x: [e.value for e in x]),
        default=CampaignStatus.DRAFT,
        nullable=False,
    )

    # Scheduling
    timezone = Column(String(50), default="UTC", nullable=False)
    send_window_start = Column(String(5), default="09:00", nullable=False)
    send_window_end = Column(String(5), default="17:00", nullable=False)
    send_days_json = Column(Text, default='["mon","tue","wed","thu","fri"]', nullable=False)

    # Mailbox assignment (JSON array of mailbox_id)
    mailbox_ids_json = Column(Text, nullable=True)

    # Limits
    daily_limit = Column(Integer, default=30, nullable=False)

    # Auto-enrollment rules (JSON) and daily counter
    enrollment_rules_json = Column(Text, nullable=True)
    auto_enrolled_today = Column(Integer, default=0, nullable=False)

    # Denormalized stats
    total_contacts = Column(Integer, default=0, nullable=False)
    total_sent = Column(Integer, default=0, nullable=False)
    total_opened = Column(Integer, default=0, nullable=False)
    total_replied = Column(Integer, default=0, nullable=False)
    total_bounced = Column(Integer, default=0, nullable=False)

    # Ownership
    created_by = Column(Integer, ForeignKey("users.user_id"), nullable=True)

    __table_args__ = (
        Index("idx_campaign_tenant", "tenant_id"),
        Index("idx_campaign_status", "status"),
        Index("idx_campaign_created_by", "created_by"),
    )

    def __repr__(self) -> str:
        return f"<Campaign(campaign_id={self.campaign_id}, name='{self.name}', status='{self.status}')>"


class SequenceStep(Base):
    """A single step in a campaign sequence (email, wait, or condition)."""

    __tablename__ = "sequence_steps"

    step_id = Column(Integer, primary_key=True, autoincrement=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.campaign_id", ondelete="CASCADE"), nullable=False)
    step_order = Column(Integer, nullable=False)
    step_type = Column(
        Enum(StepType, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )

    # Email content (step_type == email)
    subject = Column(String(500), nullable=True)
    body_html = Column(Text, nullable=True)
    body_text = Column(Text, nullable=True)
    template_id = Column(Integer, ForeignKey("email_templates.template_id"), nullable=True)

    # Delay (step_type == wait or between emails)
    delay_days = Column(Integer, default=1, nullable=False)
    delay_hours = Column(Integer, default=0, nullable=False)

    # Threading
    reply_to_thread = Column(Boolean, default=True, nullable=False)

    # Condition (step_type == condition)
    condition_type = Column(String(50), nullable=True)  # opened/clicked/replied/no_action
    condition_window_hours = Column(Integer, default=24, nullable=True)
    yes_next_step = Column(Integer, nullable=True)  # step_order to jump to if condition met
    no_next_step = Column(Integer, nullable=True)   # step_order to jump to if condition not met

    # A/B testing variants (JSON array of {subject, body_html, body_text, weight})
    variants_json = Column(Text, nullable=True)

    # Denormalized stats
    total_sent = Column(Integer, default=0, nullable=False)
    total_opened = Column(Integer, default=0, nullable=False)
    total_clicked = Column(Integer, default=0, nullable=False)
    total_replied = Column(Integer, default=0, nullable=False)
    total_bounced = Column(Integer, default=0, nullable=False)

    __table_args__ = (
        Index("idx_step_campaign_order", "campaign_id", "step_order"),
    )

    def __repr__(self) -> str:
        return f"<SequenceStep(step_id={self.step_id}, campaign_id={self.campaign_id}, order={self.step_order}, type='{self.step_type}')>"


class CampaignContact(Base):
    """Tracks a contact's progress through a campaign sequence."""

    __tablename__ = "campaign_contacts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.campaign_id", ondelete="CASCADE"), nullable=False)
    contact_id = Column(Integer, ForeignKey("contact_details.contact_id"), nullable=False)
    lead_id = Column(Integer, ForeignKey("lead_details.lead_id"), nullable=True)

    status = Column(
        Enum(CampaignContactStatus, values_callable=lambda x: [e.value for e in x]),
        default=CampaignContactStatus.ACTIVE,
        nullable=False,
    )

    current_step = Column(Integer, default=0, nullable=False)  # step_order of current/next step
    next_send_at = Column(DateTime, nullable=True)
    enrolled_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)

    # A/B variant assignments (JSON: {step_id: variant_index})
    variant_assignments_json = Column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("campaign_id", "contact_id", name="uq_campaign_contact"),
        Index("idx_cc_campaign", "campaign_id"),
        Index("idx_cc_contact", "contact_id"),
        Index("idx_cc_next_send", "next_send_at"),
        Index("idx_cc_status", "status"),
    )

    def __repr__(self) -> str:
        return f"<CampaignContact(id={self.id}, campaign_id={self.campaign_id}, contact_id={self.contact_id}, status='{self.status}')>"
