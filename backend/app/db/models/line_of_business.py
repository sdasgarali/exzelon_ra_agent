"""Line of Business (LOB) model for multi-LOB architecture."""
from enum import Enum as PyEnum
from sqlalchemy import (
    Column, Integer, String, Text, Boolean, Enum, ForeignKey,
    Index, UniqueConstraint,
)
from app.db.base import Base


class LOBType(str, PyEnum):
    """Predefined LOB types."""
    STAFFING = "staffing"
    RCM = "rcm"
    SOFTWARE_DEV = "software_dev"
    AI_SERVICES = "ai_services"
    DIGITAL_MARKETING = "digital_marketing"
    CUSTOM = "custom"


class LOBStatus(str, PyEnum):
    """LOB operational status."""
    ACTIVE = "active"
    PAUSED = "paused"


class LineOfBusiness(Base):
    """Line of Business — encapsulates LOB-specific configuration.

    Each tenant can have one or more LOBs. One LOB per tenant is marked
    as is_default=True. All LOB-specific settings (lead sources, ICP,
    business rules, AI prompts) are stored as JSON for flexibility.
    """

    __tablename__ = "lines_of_business"

    lob_id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(
        Integer,
        ForeignKey("tenants.tenant_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = Column(String(255), nullable=False)
    slug = Column(String(100), nullable=False)
    lob_type = Column(
        Enum(LOBType, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    description = Column(Text, nullable=True)

    # LOB-specific configuration (JSON)
    lead_source_config = Column(Text, nullable=True)    # which adapters + search queries
    icp_config = Column(Text, nullable=True)             # target industries, sizes, titles, geo
    business_rules = Column(Text, nullable=True)         # send limits, cooldowns, thresholds
    prompt_profile = Column(Text, nullable=True)         # AI prompt context overrides

    # LOB-specific targeting overrides (JSON arrays)
    target_industries_json = Column(Text, nullable=True)
    target_job_titles_json = Column(Text, nullable=True)
    exclude_keywords_json = Column(Text, nullable=True)

    # State
    is_default = Column(Boolean, default=False, nullable=False)
    status = Column(
        Enum(LOBStatus, values_callable=lambda x: [e.value for e in x]),
        default=LOBStatus.ACTIVE,
        nullable=False,
    )

    # UI display
    color = Column(String(7), nullable=True)   # hex color for badges, e.g. "#1A3C6E"
    icon = Column(String(50), nullable=True)   # icon identifier, e.g. "briefcase"

    __table_args__ = (
        UniqueConstraint("tenant_id", "slug", name="uq_lob_tenant_slug"),
        Index("idx_lob_tenant", "tenant_id"),
        Index("idx_lob_tenant_default", "tenant_id", "is_default"),
    )

    def __repr__(self) -> str:
        return f"<LineOfBusiness(lob_id={self.lob_id}, name='{self.name}', type='{self.lob_type}')>"
