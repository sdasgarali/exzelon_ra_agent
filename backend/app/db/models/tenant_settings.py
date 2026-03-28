"""Per-tenant settings overrides (copy-on-write)."""
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, ForeignKey, UniqueConstraint, Index,
)
from app.db.base import Base


class TenantSettings(Base):
    """Per-tenant setting overrides.

    Resolution order:
    1. TenantSettings[tenant_id, key]  <- tenant override (highest priority)
    2. Settings[key]                   <- global DB default
    3. config.py / .env                <- environment variable
    4. Caller-supplied default         <- hardcoded fallback
    """

    __tablename__ = "tenant_settings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(
        Integer,
        ForeignKey("tenants.tenant_id", ondelete="CASCADE"),
        nullable=False,
    )
    key = Column(String(100), nullable=False)
    value_json = Column(Text, nullable=True)
    updated_by = Column(String(255), nullable=True)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "key", name="uq_tenant_settings_tid_key"),
        Index("idx_tenant_settings_tid_key", "tenant_id", "key"),
    )

    def __repr__(self) -> str:
        return f"<TenantSettings(tenant_id={self.tenant_id}, key='{self.key}')>"
