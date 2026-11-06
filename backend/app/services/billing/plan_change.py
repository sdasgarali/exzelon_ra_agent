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


def _release_copied_limits(tenant, old_plan, new_plan) -> None:
    """Let the new plan's limits apply on a plan change.

    A `max_*` column > 0 overrides the plan (limits_for_tenant). Signups before
    2026-11 had Free's numbers copied into those columns, so after an upgrade they
    kept overriding the paid tier. Any column that merely equals the OLD plan's
    default is reset to 0 ("follow the plan"); a value that differs is a deliberate
    per-tenant grant and is kept. Custom plans own their row, so they are left alone.
    """
    from app.core.plans import LIMIT_FIELDS, get_plan, is_custom

    if old_plan == new_plan or is_custom(old_plan) or is_custom(new_plan):
        return
    old_spec = get_plan(old_plan)
    for field in LIMIT_FIELDS:
        current = int(getattr(tenant, field, 0) or 0)
        if current > 0 and current == getattr(old_spec, field):
            setattr(tenant, field, 0)


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
    _release_copied_limits(tenant, old_plan, new_plan)

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
