"""Credit and usage metering."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Float, Index
from app.db.base import Base


class CreditUsage(Base):
    __tablename__ = "credit_usage"

    usage_id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=True)

    usage_type = Column(String(50), nullable=False)  # ai_generation/email_validation/lead_lookup/api_call
    credits_used = Column(Float, default=1.0, nullable=False)
    description = Column(String(500), nullable=True)
    reference_id = Column(String(255), nullable=True)  # e.g. campaign_id, contact_id

    recorded_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_credit_tenant", "tenant_id"),
        Index("idx_credit_type", "usage_type"),
        Index("idx_credit_recorded", "recorded_at"),
    )

    def __repr__(self) -> str:
        return f"<CreditUsage(usage_id={self.usage_id}, type='{self.usage_type}', credits={self.credits_used})>"
