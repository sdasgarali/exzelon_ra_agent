"""Soft-bounce (4xx) tracker — counts repeated temporary failures per address so
they can be escalated to a permanent suppression after MAX_TEMP_FAILURES (ELR-015)."""
from sqlalchemy import Column, Integer, String, UniqueConstraint, Index
from app.db.base import Base


class SoftBounceTracker(Base):
    """Per-tenant, per-email count of consecutive 4xx soft bounces."""

    __tablename__ = "soft_bounce_trackers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, nullable=False, index=True)
    email = Column(String(255), nullable=False, index=True)
    count = Column(Integer, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint("tenant_id", "email", name="uq_soft_bounce_tenant_email"),
        Index("idx_soft_bounce_email", "email"),
    )
