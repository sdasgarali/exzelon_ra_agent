"""Plan feature gating (Phase 3).

Three ways to ask the same question, because the call sites genuinely differ:

* :func:`require_feature` — a FastAPI dependency. Use at router level
  (``include_router(r, dependencies=[Depends(require_feature("warmup"))])``) when an
  entire area belongs to a tier, or per-endpoint when only some routes do.
* :func:`ensure_feature` — a plain function for use inside an endpoint body or a
  service, where the feature depends on a value you only have after loading a record.
* :func:`has_feature` — a boolean, for branching rather than blocking: hiding a nav
  item, or dropping a beacon from a plan that isn't paying for it.

**402, not 403.** A 403 means "you may not"; this is "your plan doesn't include it
yet", which is a payment state and is what the credit gate already returns. The body
is a structured dict with a `code`, so the frontend can tell a feature gate from an
exhausted balance and show the right upgrade prompt instead of a generic error.
"""
from typing import Optional

import structlog
from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps.auth import get_current_tenant_id
from app.api.deps.database import get_db
from app.core.plans import (
    feature_label, minimum_plan_for, normalize_plan, plan_features, PLAN_MATRIX,
)

logger = structlog.get_logger()

#: Machine-readable discriminator in the 402 body. The credit gate uses its own.
FEATURE_GATE_CODE = "feature_not_in_plan"


def _tenant_plan(db: Session, tenant_id: int) -> str:
    from app.db.models.tenant import Tenant
    tenant = db.query(Tenant).filter(Tenant.tenant_id == tenant_id).first()
    return normalize_plan(getattr(tenant, "plan", None))


def has_feature(db: Session, tenant_id: Optional[int], feature: str) -> bool:
    """Whether the tenant's plan includes `feature`.

    Super admins (`tenant_id is None`) always get True — they operate across tenants
    and are not on a plan.
    """
    if tenant_id is None:
        return True
    return feature in plan_features(_tenant_plan(db, tenant_id))


def ensure_feature(db: Session, tenant_id: Optional[int], feature: str) -> None:
    """Raise 402 unless the tenant's plan includes `feature`."""
    if tenant_id is None:
        return

    plan = _tenant_plan(db, tenant_id)
    if feature in plan_features(plan):
        return

    label = feature_label(feature)
    required = minimum_plan_for(feature)
    required_label = PLAN_MATRIX[required].label if required else None

    if required_label:
        message = f"{label} is available on {required_label} and above. Upgrade to unlock it."
    else:
        # No tier grants it — a misconfigured feature key rather than a real upsell.
        message = f"{label} is not available on your plan."

    logger.info("feature_gate_blocked", tenant_id=tenant_id, feature=feature,
                plan=plan, required_plan=required)
    raise HTTPException(
        status_code=status.HTTP_402_PAYMENT_REQUIRED,
        detail={
            "code": FEATURE_GATE_CODE,
            "feature": feature,
            "feature_label": label,
            "plan": plan,
            "required_plan": required,
            "message": message,
        },
    )


def require_feature(feature: str):
    """FastAPI dependency factory: block the request unless the plan includes `feature`."""

    def _dep(
        db: Session = Depends(get_db),
        tenant_id: Optional[int] = Depends(get_current_tenant_id),
    ) -> None:
        ensure_feature(db, tenant_id, feature)

    # Tagged so the gate can be audited by walking the mounted routes rather than by
    # keeping a hand-maintained list in the tests — see
    # `tests/security/test_feature_gate_coverage.py`. A typo'd key is otherwise
    # invisible: `require_feature("warmupp")` is in no plan, so it locks out every
    # tier including Max, and the 402 message reads like a deliberate product
    # decision instead of a bug.
    _dep.__feature__ = feature  # type: ignore[attr-defined]
    _dep.__name__ = f"require_feature[{feature}]"
    return _dep
