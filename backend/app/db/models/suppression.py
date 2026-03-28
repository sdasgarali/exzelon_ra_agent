"""Suppression list model for do-not-contact entries."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, Index, ForeignKey
from app.db.base import Base


class SuppressionList(Base):
    """Suppression list model - Do-not-contact list."""

    __tablename__ = "suppression_list"

    suppression_id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    reason = Column(Text, nullable=True)  # e.g., "unsubscribed", "bounced", "manual"
    expires_at = Column(DateTime, nullable=True)  # Optional expiry

    __table_args__ = (
        Index('idx_suppression_email', 'email'),
        Index('idx_suppression_tenant', 'tenant_id'),
    )

    def __repr__(self) -> str:
        return f"<SuppressionList(suppression_id={self.suppression_id}, email='{self.email}')>"
