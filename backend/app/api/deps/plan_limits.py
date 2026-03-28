"""Plan limit enforcement for multi-tenancy."""
from typing import Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.db.models.tenant import Tenant, TenantPlan
from app.db.models.lead import LeadDetails
from app.db.models.contact import ContactDetails
from app.db.models.sender_mailbox import SenderMailbox
from app.db.models.campaign import Campaign
from app.db.models.user import User


# Resource count queries
RESOURCE_COUNTERS = {
    "leads": lambda db, tid: db.query(LeadDetails).filter(LeadDetails.tenant_id == tid).count(),
    "contacts": lambda db, tid: db.query(ContactDetails).filter(ContactDetails.tenant_id == tid).count(),
    "mailboxes": lambda db, tid: db.query(SenderMailbox).filter(SenderMailbox.tenant_id == tid).count(),
    "campaigns": lambda db, tid: db.query(Campaign).filter(Campaign.tenant_id == tid).count(),
    "users": lambda db, tid: db.query(User).filter(User.tenant_id == tid, User.is_active == True).count(),
}

# Limit field names on Tenant model
RESOURCE_LIMITS = {
    "leads": "max_leads",
    "contacts": "max_contacts",
    "mailboxes": "max_mailboxes",
    "campaigns": "max_campaigns",
    "users": "max_users",
}


def check_plan_limit(
    db: Session,
    tenant_id: Optional[int],
    resource: str,
) -> None:
    """Raise 403 if tenant exceeds plan limit for the given resource.

    Args:
        db: Database session
        tenant_id: Tenant ID (None = super admin, skip check)
        resource: Resource type key (leads, contacts, mailboxes, campaigns, users)

    Raises:
        HTTPException 403 if limit exceeded
    """
    # Super admin bypass
    if tenant_id is None:
        return

    tenant = db.query(Tenant).filter(Tenant.tenant_id == tenant_id).first()
    if not tenant:
        return

    # Enterprise plan has no limits
    if tenant.plan == TenantPlan.ENTERPRISE:
        return

    limit_field = RESOURCE_LIMITS.get(resource)
    if not limit_field:
        return

    max_allowed = getattr(tenant, limit_field, 0)

    # 0 means unlimited for professional, but locked for starter
    if max_allowed == 0 and tenant.plan == TenantPlan.STARTER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Starter plan does not include {resource}. Upgrade to Professional to unlock.",
        )

    if max_allowed == 0:
        # Professional with 0 = unlimited
        return

    counter = RESOURCE_COUNTERS.get(resource)
    if not counter:
        return

    current_count = counter(db, tenant_id)
    if current_count >= max_allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Plan limit reached: {current_count}/{max_allowed} {resource}. Upgrade your plan for more.",
        )


def check_starter_readonly(
    tenant_id: Optional[int],
    plan: Optional[str],
) -> None:
    """Raise 403 if tenant is on starter plan (read-only mode).

    Used for endpoints where starter plan users shouldn't create/modify data.

    Args:
        tenant_id: Tenant ID (None = super admin, skip)
        plan: Plan string from JWT token
    """
    if tenant_id is None:
        return
    if plan == TenantPlan.STARTER.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Upgrade to Professional to unlock this feature.",
        )
