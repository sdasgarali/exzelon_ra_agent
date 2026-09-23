"""Tenant creation and management service."""
import re
from sqlalchemy.orm import Session
import structlog

from app.core.plans import PLAN_MATRIX, DEFAULT_PLAN
from app.db.models.tenant import Tenant, TenantPlan

logger = structlog.get_logger()


def generate_unique_slug(company_name: str, db: Session) -> str:
    """Generate a unique slug from a company name.

    Args:
        company_name: The raw company name.
        db: Database session to check for collisions.

    Returns:
        A unique URL-safe slug string.
    """
    slug = company_name.lower().strip()
    slug = re.sub(r'[^a-z0-9\s-]', '', slug)
    slug = re.sub(r'[\s-]+', '-', slug)
    slug = slug.strip('-')[:100]
    if not slug:
        slug = "org"

    base_slug = slug
    counter = 2
    while db.query(Tenant).filter(Tenant.slug == slug).first() is not None:
        slug = f"{base_slug}-{counter}"
        counter += 1

    return slug


def create_tenant_for_signup(company_name: str, db: Session) -> Tenant:
    """Create a new Free tenant for self-service signup.

    Limits come from `PLAN_MATRIX["free"]`, never hardcoded here. Until 2026-09 this
    function assigned `max_mailboxes/contacts/campaigns/leads = 0`, which the old
    plan-limit sentinel read as "locked" — so every self-signup tenant was created
    unable to add a mailbox, lead, contact or campaign. Reading the matrix means a
    pricing change can never silently strand new signups again.

    Args:
        company_name: The company name from the signup form.
        db: Database session.

    Returns:
        The created Tenant record.
    """
    slug = generate_unique_slug(company_name, db)

    free = PLAN_MATRIX[DEFAULT_PLAN]
    tenant = Tenant(
        name=company_name,
        slug=slug,
        plan=TenantPlan(DEFAULT_PLAN),
        max_users=free.max_users,
        max_mailboxes=free.max_mailboxes,
        max_contacts=free.max_contacts,
        max_campaigns=free.max_campaigns,
        max_leads=free.max_leads,
        max_lobs=free.max_lobs,
        monthly_price_cents=free.monthly_price_cents,
    )
    db.add(tenant)
    db.commit()
    db.refresh(tenant)

    # Every tenant gets its own CRM pipeline stages up front.
    try:
        from app.services.deal_automation import ensure_deal_stages
        if ensure_deal_stages(db, tenant.tenant_id):
            db.commit()
    except Exception as e:
        logger.warning("Failed to seed deal stages for new tenant", tenant_id=tenant.tenant_id, error=str(e))

    logger.info("Created tenant", tenant_id=tenant.tenant_id, name=company_name, slug=slug)
    return tenant
