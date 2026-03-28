"""Webhook and WebhookDelivery models for event notifications."""
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, DateTime, Text, Boolean,
    ForeignKey, Index,
)
from app.db.base import Base


class Webhook(Base):
    """Webhook subscription — notifies external URLs on events."""

    __tablename__ = "webhooks"

    webhook_id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    url = Column(String(1000), nullable=False)
    secret = Column(String(255), nullable=True)  # HMAC signing secret
    events_json = Column(Text, nullable=False)    # JSON array of event types
    is_active = Column(Boolean, default=True, nullable=False)
    last_triggered_at = Column(DateTime, nullable=True)
    total_deliveries = Column(Integer, default=0, nullable=False)
    total_failures = Column(Integer, default=0, nullable=False)
    created_by = Column(Integer, ForeignKey("users.user_id"), nullable=True)

    __table_args__ = (
        Index("idx_webhook_active", "is_active"),
        Index("idx_webhook_tenant", "tenant_id"),
    )

    def __repr__(self) -> str:
        return f"<Webhook(webhook_id={self.webhook_id}, name='{self.name}', active={self.is_active})>"


class WebhookDelivery(Base):
    """Individual webhook delivery attempt log."""

    __tablename__ = "webhook_deliveries"

    delivery_id = Column(Integer, primary_key=True, autoincrement=True)
    webhook_id = Column(Integer, ForeignKey("webhooks.webhook_id", ondelete="CASCADE"), nullable=False)
    event = Column(String(100), nullable=False)
    payload_json = Column(Text, nullable=False)
    response_status = Column(Integer, nullable=True)
    response_body = Column(Text, nullable=True)
    success = Column(Boolean, default=False, nullable=False)
    attempt_count = Column(Integer, default=1, nullable=False)
    next_retry_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("idx_delivery_webhook", "webhook_id"),
        Index("idx_delivery_event", "event"),
    )

    def __repr__(self) -> str:
        return f"<WebhookDelivery(delivery_id={self.delivery_id}, webhook={self.webhook_id}, event='{self.event}', success={self.success})>"
