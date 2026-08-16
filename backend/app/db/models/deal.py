"""Deal pipeline models — CRM-style deal tracking."""
from sqlalchemy import (
    Column, Integer, String, DateTime, Text, Boolean, Numeric,
    ForeignKey, Index, Date,
)
from app.db.base import Base


class DealStage(Base):
    """Pipeline stage definition."""

    __tablename__ = "deal_stages"

    stage_id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    stage_order = Column(Integer, nullable=False)
    color = Column(String(7), default="#6b7280", nullable=False)  # hex color
    is_won = Column(Boolean, default=False, nullable=False)
    is_lost = Column(Boolean, default=False, nullable=False)

    __table_args__ = (
        Index("idx_stage_order", "stage_order"),
        Index("idx_stage_tenant", "tenant_id"),
    )

    def __repr__(self) -> str:
        return f"<DealStage(stage_id={self.stage_id}, name='{self.name}', order={self.stage_order})>"


class Deal(Base):
    """A deal/opportunity in the CRM pipeline."""

    __tablename__ = "deals"

    deal_id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    stage_id = Column(Integer, ForeignKey("deal_stages.stage_id"), nullable=False)

    # Relationships
    contact_id = Column(Integer, ForeignKey("contact_details.contact_id"), nullable=True)
    client_id = Column(Integer, ForeignKey("client_info.client_id"), nullable=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.campaign_id"), nullable=True)

    # Deal info
    value = Column(Numeric(12, 2), default=0, nullable=False)
    probability = Column(Integer, default=0, nullable=False)  # 0-100
    expected_close_date = Column(Date, nullable=True)

    # Ownership — owner_id is the admin-ASSIGNED owner (rep the deal is assigned to).
    owner_id = Column(Integer, ForeignKey("users.user_id"), nullable=True)

    # Claim queue — a BDM/Recruiter CLAIMS an unclaimed deal (self-pull). NULL = Unclaimed.
    # Distinct from owner_id (which an admin assigns). Drives the Unclaimed/initials tag.
    claimed_by_user_id = Column(Integer, ForeignKey("users.user_id"), nullable=True, index=True)
    claimed_at = Column(DateTime, nullable=True)

    # Notes
    notes = Column(Text, nullable=True)

    # Automation flags
    is_auto_created = Column(Boolean, default=False, nullable=False)
    probability_manual = Column(Boolean, default=False, nullable=False)

    # Outcome
    won_at = Column(DateTime, nullable=True)
    lost_at = Column(DateTime, nullable=True)
    lost_reason = Column(Text, nullable=True)

    __table_args__ = (
        Index("idx_deal_stage", "stage_id"),
        Index("idx_deal_contact", "contact_id"),
        Index("idx_deal_client", "client_id"),
        Index("idx_deal_tenant", "tenant_id"),
        Index("idx_deal_claimed_by", "claimed_by_user_id"),
    )

    def __repr__(self) -> str:
        return f"<Deal(deal_id={self.deal_id}, name='{self.name}', stage={self.stage_id})>"


class DealCandidate(Base):
    """A candidate a recruiter submits against a deal (the recruiting hand-off).

    Distinct from the Resource Pool ATS candidate records — this is the in-app
    submission tracked through the recruiter → BDM → client pipeline.
    """

    __tablename__ = "deal_candidates"

    candidate_id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    deal_id = Column(Integer, ForeignKey("deals.deal_id", ondelete="CASCADE"), nullable=False, index=True)

    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=True)
    phone = Column(String(64), nullable=True)
    linkedin_url = Column(String(500), nullable=True)
    resume_url = Column(String(500), nullable=True)

    # submitted → reviewed (by BDM) → sent_to_client → placed / rejected
    status = Column(String(30), default="submitted", nullable=False)
    notes = Column(Text, nullable=True)
    submitted_by_user_id = Column(Integer, ForeignKey("users.user_id"), nullable=True)

    __table_args__ = (
        Index("idx_deal_candidate_deal", "deal_id"),
        Index("idx_deal_candidate_tenant", "tenant_id"),
    )

    def __repr__(self) -> str:
        return f"<DealCandidate(candidate_id={self.candidate_id}, deal={self.deal_id}, name='{self.name}', status='{self.status}')>"


class DealActivity(Base):
    """Activity log entry for a deal."""

    __tablename__ = "deal_activities"

    activity_id = Column(Integer, primary_key=True, autoincrement=True)
    deal_id = Column(Integer, ForeignKey("deals.deal_id", ondelete="CASCADE"), nullable=False)
    activity_type = Column(String(50), nullable=False)  # note/stage_change/email_sent/email_received/call
    description = Column(Text, nullable=True)
    metadata_json = Column(Text, nullable=True)
    created_by = Column(Integer, ForeignKey("users.user_id"), nullable=True)

    __table_args__ = (
        Index("idx_activity_deal", "deal_id"),
    )

    def __repr__(self) -> str:
        return f"<DealActivity(activity_id={self.activity_id}, deal={self.deal_id}, type='{self.activity_type}')>"
