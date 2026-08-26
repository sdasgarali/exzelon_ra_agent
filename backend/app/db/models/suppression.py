"""Suppression list model for do-not-contact entries."""
from sqlalchemy import Column, Integer, String, DateTime, Text, Index, ForeignKey, UniqueConstraint
from app.db.base import Base


class SuppressionList(Base):
    """Suppression list model - Do-not-contact list.

    Uniqueness is per-tenant (tenant_id, email), NOT global-on-email: each tenant
    owns its own opt-outs, so one tenant unsubscribing an address must not block
    another tenant from having its own record (the old email-unique constraint
    caused cross-tenant insert failures). The send gate still checks suppression
    by email globally for safety. (ELR-016)
    """

    __tablename__ = "suppression_list"

    suppression_id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.tenant_id"), nullable=False, index=True)

    # Line of Business (nullable — NULL = suppressed across all LOBs)
    lob_id = Column(Integer, ForeignKey("lines_of_business.lob_id", ondelete="SET NULL"), nullable=True, index=True)
    email = Column(String(255), nullable=False, index=True)
    reason = Column(Text, nullable=True)  # e.g., "unsubscribed", "bounced", "manual"
    expires_at = Column(DateTime, nullable=True)  # Optional expiry

    __table_args__ = (
        UniqueConstraint('tenant_id', 'email', name='uq_suppression_tenant_email'),
        Index('idx_suppression_email', 'email'),
        Index('idx_suppression_tenant', 'tenant_id'),
    )

    def __repr__(self) -> str:
        return f"<SuppressionList(suppression_id={self.suppression_id}, email='{self.email}')>"
