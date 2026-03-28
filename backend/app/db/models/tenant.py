"""Multi-tenant model for organization isolation."""
from enum import Enum as PyEnum
from sqlalchemy import (
    Column, Integer, String, Text, Boolean, Enum,
)
from app.db.base import Base


class TenantPlan(str, PyEnum):
    """Tenant subscription plans."""
    STARTER = "starter"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"


class Tenant(Base):
    """Tenant representing an organization/company."""

    __tablename__ = "tenants"

    tenant_id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    slug = Column(String(100), nullable=False, unique=True, index=True)
    domain = Column(String(255), nullable=True)
    logo_url = Column(String(500), nullable=True)
    plan = Column(
        Enum(TenantPlan, values_callable=lambda x: [e.value for e in x]),
        default=TenantPlan.STARTER,
        nullable=False,
    )
    is_active = Column(Boolean, default=True, nullable=False)
    settings_json = Column(Text, nullable=True)
    max_users = Column(Integer, default=3, nullable=False)
    max_mailboxes = Column(Integer, default=0, nullable=False)
    max_contacts = Column(Integer, default=0, nullable=False)
    max_campaigns = Column(Integer, default=0, nullable=False)
    max_leads = Column(Integer, default=0, nullable=False)

    def __repr__(self) -> str:
        return f"<Tenant(tenant_id={self.tenant_id}, slug='{self.slug}', plan='{self.plan}')>"
