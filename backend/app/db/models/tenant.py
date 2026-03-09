"""Multi-tenant model for white-label support (Phase 4)."""
from sqlalchemy import (
    Column, Integer, String, Text, Boolean,
)
from app.db.base import Base


class Tenant(Base):
    """Tenant for white-label multi-tenancy."""

    __tablename__ = "tenants"

    tenant_id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    slug = Column(String(100), nullable=False, unique=True)
    domain = Column(String(255), nullable=True)
    logo_url = Column(String(500), nullable=True)
    primary_color = Column(String(7), default="#2563eb", nullable=False)
    plan = Column(String(50), default="free", nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    settings_json = Column(Text, nullable=True)
    max_mailboxes = Column(Integer, default=10, nullable=False)
    max_contacts = Column(Integer, default=10000, nullable=False)
    max_campaigns = Column(Integer, default=50, nullable=False)

    def __repr__(self) -> str:
        return f"<Tenant(tenant_id={self.tenant_id}, slug='{self.slug}')>"
