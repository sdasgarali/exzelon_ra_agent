"""API key model for programmatic access."""
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, DateTime, Text, Boolean,
    ForeignKey, Index,
)
from app.db.base import Base


class ApiKey(Base):
    """API key for external integrations (Zapier, Make, custom)."""

    __tablename__ = "api_keys"

    key_id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    key_hash = Column(String(64), nullable=False, unique=True)  # SHA-256 hex
    key_prefix = Column(String(8), nullable=False)  # first 8 chars for display
    scopes_json = Column(Text, nullable=True)  # JSON array of scope strings
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    last_used_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("idx_apikey_hash", "key_hash"),
        Index("idx_apikey_user", "user_id"),
        Index("idx_apikey_active", "is_active"),
        Index("idx_apikey_tenant", "tenant_id"),
    )

    def __repr__(self) -> str:
        return f"<ApiKey(key_id={self.key_id}, name='{self.name}', prefix='{self.key_prefix}...')>"
