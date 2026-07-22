"""Attribution rows recorded from Resource Pool outcome webhooks.

Each row links a downstream recruiting outcome (offer accepted, placement created,
invoice paid) back to the RA Agent lead/source/campaign that originated it — closing
the loop from cold-outreach campaign → placement → revenue.
"""
from sqlalchemy import (
    Column, Integer, String, Numeric, Text, DateTime, ForeignKey, Index, UniqueConstraint,
)

from app.db.base import Base


class ResourcePoolAttribution(Base):
    __tablename__ = "resource_pool_attributions"

    attribution_id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.tenant_id"), nullable=False, index=True)

    # Event
    event_type = Column(String(50), nullable=False, index=True)  # offer.accepted / placement.created / invoice.paid
    rp_entity_id = Column(String(64), nullable=True, index=True)  # placement/offer/invoice id (idempotency key)

    # Attribution linkage back to the RA side
    external_ref = Column(String(120), nullable=True, index=True)  # "ra-lead-<id>"
    lead_id = Column(Integer, ForeignKey("lead_details.lead_id", ondelete="SET NULL"), nullable=True, index=True)
    campaign_id = Column(Integer, nullable=True, index=True)
    source = Column(String(100), nullable=True, index=True)  # originating lead source

    # Value
    amount = Column(Numeric(12, 2), nullable=True)   # offerAmount / invoice amount / bill rate (per event_type)
    currency = Column(String(8), nullable=True, default="USD")

    occurred_at = Column(DateTime, nullable=True)    # webhook createdAt
    raw_json = Column(Text, nullable=True)           # full webhook data payload

    __table_args__ = (
        # Idempotent on repeated webhook delivery of the same entity+event.
        UniqueConstraint("tenant_id", "event_type", "rp_entity_id", name="uq_rp_attr_entity"),
        Index("idx_rp_attr_tenant_source", "tenant_id", "source"),
        Index("idx_rp_attr_lead", "lead_id"),
    )

    def __repr__(self) -> str:
        return f"<ResourcePoolAttribution({self.event_type} ext={self.external_ref} amount={self.amount})>"
