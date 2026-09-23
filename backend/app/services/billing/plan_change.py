"""The one way a tenant's plan changes.

A plan change is more than `tenant.plan = ...`: the monthly credit allowance has to move
with it, or an upgrade pays for credits that only arrive on the 1st and a downgrade keeps
the old allowance. Every caller — the Stripe webhook, the super-admin tenant editor —
goes through :func:`change_plan` so the two can never drift apart again.
"""
from typing import Optional

import structlog
from sqlalchemy.orm import Session

from app.db.models.tenant import TenantPlan
from app.services.credit_metering import adjust_allowance_for_plan_change, plan_credit_limit

logger = structlog.get_logger()


def change_plan(db: Session, tenant, new_plan: TenantPlan, *, reason: str,
                old_allowance: Optional[int] = None) -> bool:
    """Set `tenant.plan` and move this month's credit allowance with it.

    `old_allowance` is for callers that change other allowance inputs in the same
    request (a Custom tenant's `credits_per_month`) and snapshotted it beforehand.
    Does not commit — the caller owns the transaction. Returns True when anything
    changed.
    """
    if old_allowance is None:
        old_allowance = plan_credit_limit(getattr(tenant, "plan", None), tenant=tenant)
    old_plan = tenant.plan
    tenant.plan = new_plan

    applied = adjust_allowance_for_plan_change(db, tenant, old_allowance)
    changed = old_plan != new_plan or applied != 0
    if changed:
        logger.info(
            "tenant_plan_changed",
            tenant_id=tenant.tenant_id,
            old_plan=getattr(old_plan, "value", old_plan),
            new_plan=getattr(new_plan, "value", new_plan),
            credits_applied=applied,
            reason=reason,
        )
    return changed
