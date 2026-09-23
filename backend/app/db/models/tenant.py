"""Multi-tenant model for organization isolation."""
from enum import Enum as PyEnum
from sqlalchemy import (
    Column, Integer, String, Text, Boolean, Enum, Numeric,
)
from app.db.base import Base


class TenantPlan(str, PyEnum):
    """Tenant subscription plans.

    Renamed 2026-09 from starter/professional/enterprise. The three old names are kept
    below as *enum aliases* — because they repeat an existing value, Python binds them
    to the same member rather than creating new ones, so `TenantPlan.STARTER is
    TenantPlan.FREE` and existing call sites keep working. Iteration and
    `values_callable` still yield only the four canonical members, which is what the
    DB enum is built from.

    Plan strings arriving from outside (JWT claims, API payloads, legacy rows) go
    through `core.plans.normalize_plan()` instead — `TenantPlan("starter")` raises,
    since "starter" is no longer a value.
    """
    FREE = "free"
    PRO = "pro"
    MAX = "max"
    CUSTOM = "custom"

    # Deprecated aliases — remove one release after the rename migration ships.
    STARTER = "free"
    PROFESSIONAL = "pro"
    ENTERPRISE = "max"


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
        default=TenantPlan.FREE,
        nullable=False,
    )
    is_active = Column(Boolean, default=True, nullable=False)
    settings_json = Column(Text, nullable=True)
    # Resource caps, resolved by core.plans.limits_for_tenant().
    #   0   = not configured for this tenant -> the plan's number applies
    #   > 0 = an explicit per-tenant cap (support grant, trial bump, custom contract)
    # It is NEVER "unlimited" — no tier is. Defaulting these to 0 rather than to a
    # tier's figures is what lets a pricing change reach existing customers with no
    # backfill, and what makes a half-provisioned row self-heal instead of locking
    # the tenant out.
    max_users = Column(Integer, default=0, nullable=False)
    max_mailboxes = Column(Integer, default=0, nullable=False)
    max_contacts = Column(Integer, default=0, nullable=False)
    max_campaigns = Column(Integer, default=0, nullable=False)
    max_leads = Column(Integer, default=0, nullable=False)
    max_lobs = Column(Integer, default=0, nullable=False, server_default="0")

    # White-label branding
    brand_name = Column(String(255), nullable=True)
    brand_logo_url = Column(String(500), nullable=True)
    brand_primary_color = Column(String(7), nullable=True)  # #hex
    brand_secondary_color = Column(String(7), nullable=True)
    custom_domain = Column(String(255), nullable=True)
    agency_mode = Column(Boolean, default=False, nullable=False)

    # Tenant profile
    website = Column(String(500), nullable=True)
    industry = Column(String(100), nullable=True)
    company_address = Column(String(500), nullable=True)
    phone = Column(String(50), nullable=True)
    contact_email = Column(String(255), nullable=True)

    # Billing
    monthly_price_cents = Column(Integer, default=0, nullable=False)
    billing_email = Column(String(255), nullable=True)
    billing_address_json = Column(Text, nullable=True)
    stripe_customer_id = Column(String(100), nullable=True, index=True)
    tax_rate_percent = Column(Numeric(5, 2), default=0, nullable=False)
    # Set when a tenant is past-due beyond the grace window; blocks spend actions
    # until they pay. Checked in the auth dependency. (ELR-023)
    billing_suspended = Column(Boolean, default=False, nullable=False, server_default="0")

    def __repr__(self) -> str:
        return f"<Tenant(tenant_id={self.tenant_id}, slug='{self.slug}', plan='{self.plan}')>"
