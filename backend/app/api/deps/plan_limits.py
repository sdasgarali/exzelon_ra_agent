"""Plan limit enforcement for multi-tenancy.

Limits resolve through `core.plans.limits_for_tenant()`: a tenant's `max_*` column of
`0` means "not configured — use the plan's number", and any positive value is an
explicit per-tenant limit.

Sentinel rule (changed 2026-09): `0` used to mean "unlimited" on professional and
"locked" on starter — the same value with two opposite meanings, which is how
self-signup tenants ended up provisioned with all-zero limits and locked out of their
own accounts. Those rows now fall back to the plan instead. `0` never means unlimited;
no tier is unlimited, and whether a tenant may use a feature at all is a feature-gate
question rather than a limit.
"""
from typing import Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.plans import limits_for_tenant, get_plan, normalize_plan
from app.db.models.tenant import Tenant, TenantPlan
from app.db.models.lead import LeadDetails
from app.db.models.contact import ContactDetails
from app.db.models.sender_mailbox import SenderMailbox
from app.db.models.campaign import Campaign, CampaignStatus
from app.db.models.line_of_business import LineOfBusiness
from app.db.models.user import User


# Campaigns that occupy a slot: only these hold enrolments and get swept by the
# campaign engine every two minutes. DRAFT costs nothing to keep, and COMPLETED /
# ARCHIVED campaigns release their slot — otherwise the cap is a one-way ratchet
# that locks a tenant out with nothing actually running.
LIVE_CAMPAIGN_STATUSES = (CampaignStatus.ACTIVE, CampaignStatus.PAUSED)


# Resource count queries
RESOURCE_COUNTERS = {
    "leads": lambda db, tid: db.query(LeadDetails).filter(LeadDetails.tenant_id == tid).count(),
    "contacts": lambda db, tid: db.query(ContactDetails).filter(ContactDetails.tenant_id == tid).count(),
    "mailboxes": lambda db, tid: db.query(SenderMailbox).filter(SenderMailbox.tenant_id == tid).count(),
    "campaigns": lambda db, tid: db.query(Campaign).filter(
        Campaign.tenant_id == tid,
        Campaign.status.in_(LIVE_CAMPAIGN_STATUSES),
    ).count(),
    "lobs": lambda db, tid: db.query(LineOfBusiness).filter(LineOfBusiness.tenant_id == tid).count(),
    "users": lambda db, tid: db.query(User).filter(User.tenant_id == tid, User.is_active == True).count(),
}

# Limit field names, as exposed by core.plans.limits_for_tenant()
RESOURCE_LIMITS = {
    "leads": "max_leads",
    "contacts": "max_contacts",
    "mailboxes": "max_mailboxes",
    "campaigns": "max_campaigns",
    "lobs": "max_lobs",
    "users": "max_users",
}

# Human-readable resource names for the 403 body.
RESOURCE_LABELS = {
    "leads": "leads",
    "contacts": "contacts",
    "mailboxes": "mailboxes",
    "campaigns": "active campaigns",
    "lobs": "lines of business",
    "users": "users",
}


def _next_plan_hint(plan_key: str) -> str:
    """The upgrade to suggest. Max/custom customers get told to talk to us instead."""
    return {
        "free": "Upgrade to Pro for more.",
        "pro": "Upgrade to Max for more.",
    }.get(plan_key, "Contact us about a custom plan for more.")


def check_plan_limit(
    db: Session,
    tenant_id: Optional[int],
    resource: str,
) -> None:
    """Raise 403 if the tenant is at its plan limit for the given resource.

    Args:
        db: Database session
        tenant_id: Tenant ID (None = super admin, skip check)
        resource: One of RESOURCE_COUNTERS (leads, contacts, mailboxes, campaigns,
            lobs, users)

    Raises:
        HTTPException 403 if the limit is reached or the resource is not in the plan.
    """
    # Super admin bypass
    if tenant_id is None:
        return

    tenant = db.query(Tenant).filter(Tenant.tenant_id == tenant_id).first()
    if not tenant:
        return

    limit_field = RESOURCE_LIMITS.get(resource)
    counter = RESOURCE_COUNTERS.get(resource)
    if not limit_field or not counter:
        return

    plan_key = normalize_plan(tenant.plan)
    max_allowed = limits_for_tenant(tenant).get(limit_field, 0)
    label = RESOURCE_LABELS.get(resource, resource)

    # Defensive: limits_for_tenant() always resolves to the plan's positive number, so
    # this only fires if a plan is ever configured with a zero.
    if max_allowed <= 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Your plan does not include {label}. {_next_plan_hint(plan_key)}",
        )

    current_count = counter(db, tenant_id)
    if current_count >= max_allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Plan limit reached: {current_count}/{max_allowed} {label}. "
                f"{_next_plan_hint(plan_key)}"
            ),
        )


def check_free_readonly(
    tenant_id: Optional[int],
    plan: Optional[str],
) -> None:
    """Raise 403 if the tenant is on the Free plan.

    For endpoints Free tenants shouldn't reach at all. Prefer the feature gate
    (Phase 3) for anything finer-grained than "paid plans only".
    """
    if tenant_id is None:
        return
    if normalize_plan(plan) == "free":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Upgrade to Pro to unlock this feature.",
        )


#: Deprecated alias kept so existing imports keep working. Remove with the other
#: starter/professional/enterprise leftovers.
check_starter_readonly = check_free_readonly
