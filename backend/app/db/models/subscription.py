"""Recurring subscription record — mirrors a Stripe Subscription for a tenant (ELR-021)."""
from enum import Enum as PyEnum
from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Enum, Index
from app.db.base import Base


class SubscriptionStatus(str, PyEnum):
    """Mirrors Stripe subscription statuses we care about."""
    ACTIVE = "active"
    TRIALING = "trialing"
    PAST_DUE = "past_due"
    CANCELED = "canceled"
    INCOMPLETE = "incomplete"
    UNPAID = "unpaid"


class SubscriptionRecord(Base):
    """One current subscription per tenant, kept in sync from Stripe webhooks."""

    __tablename__ = "subscriptions"

    subscription_id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    stripe_subscription_id = Column(String(100), nullable=True, unique=True, index=True)
    stripe_customer_id = Column(String(100), nullable=True, index=True)
    stripe_price_id = Column(String(100), nullable=True)
    plan = Column(String(50), nullable=True)  # starter/professional/enterprise
    status = Column(
        Enum(SubscriptionStatus, values_callable=lambda x: [e.value for e in x]),
        default=SubscriptionStatus.INCOMPLETE,
        nullable=False,
    )
    current_period_end = Column(DateTime, nullable=True)
    cancel_at_period_end = Column(Boolean, default=False, nullable=False)

    __table_args__ = (
        Index("idx_subscription_tenant", "tenant_id"),
    )
