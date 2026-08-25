"""Credit usage tracking and metering."""
import structlog
from datetime import datetime, timedelta
from typing import Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.db.models.credit_usage import CreditUsage
from app.db.query_helpers import tenant_filter

logger = structlog.get_logger()


def plan_credit_limit(plan: Optional[str]) -> int:
    """Monthly credit ceiling for a plan (0 = unlimited). Config-driven (ELR-009)."""
    from app.core.config import settings
    p = (plan or "").lower()
    return {
        "starter": settings.CREDIT_LIMIT_STARTER,
        "professional": settings.CREDIT_LIMIT_PROFESSIONAL,
        "enterprise": settings.CREDIT_LIMIT_ENTERPRISE,
    }.get(p, settings.CREDIT_LIMIT_STARTER)


def month_usage(db: Session, tenant_id: int) -> float:
    """Total credits used by a tenant in the current calendar month."""
    month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    q = db.query(func.sum(CreditUsage.credits_used)).filter(
        CreditUsage.is_archived == False,
        CreditUsage.recorded_at >= month_start,
    )
    q = tenant_filter(q, CreditUsage, tenant_id)
    return float(q.scalar() or 0)


def enforcement_enabled(db: Session, tenant_id: Optional[int]) -> bool:
    """Whether credit enforcement is active — global config OR per-tenant opt-in.

    Defaults OFF so turning it on is always an explicit decision and never breaks
    a live pipeline silently. (ELR-009)
    """
    from app.core.config import settings
    from app.core.settings_resolver import get_tenant_setting_bool
    if settings.CREDIT_ENFORCEMENT_ENABLED:
        return True
    return get_tenant_setting_bool(db, "credit_enforcement_enabled", tenant_id=tenant_id, default=False)


def check_credit_budget(
    db: Session,
    tenant_id: Optional[int],
    plan: Optional[str] = None,
    credits_needed: float = 1.0,
) -> None:
    """Pre-flight budget guard for a paid action. Raises HTTP 402 when enabled and
    the tenant's month-to-date usage + this request would exceed the plan ceiling.

    A no-op unless enforcement is enabled (see :func:`enforcement_enabled`) — so it
    is safe to call at every paid choke-point without changing current behaviour.

    NOTE: this is a sum-then-check guard; under heavy concurrency it can admit a
    small overage. A per-tenant balance row with SELECT ... FOR UPDATE is the
    hardening follow-up tracked in the ledger. (ELR-009)
    """
    if tenant_id is None:
        return  # super-admin / internal: not metered
    if not enforcement_enabled(db, tenant_id):
        return
    if plan is None:
        from app.db.models.tenant import Tenant
        tenant = db.query(Tenant).filter(Tenant.tenant_id == tenant_id).first()
        if tenant is not None:
            plan = tenant.plan.value if hasattr(tenant.plan, "value") else str(tenant.plan)
    ceiling = plan_credit_limit(plan)
    if ceiling <= 0:
        return  # unlimited
    used = month_usage(db, tenant_id)
    if used + credits_needed > ceiling:
        logger.warning("credit_budget_exceeded", tenant_id=tenant_id,
                       used=used, needed=credits_needed, ceiling=ceiling)
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Monthly credit limit reached ({int(used)}/{ceiling}). Upgrade your plan for more.",
        )


def record_usage(
    db: Session,
    tenant_id: int,
    usage_type: str,
    credits: float = 1.0,
    description: str = None,
    user_id: int = None,
    reference_id: str = None,
) -> CreditUsage:
    """Record a credit usage entry.

    Args:
        db: Database session.
        tenant_id: Tenant scope.
        usage_type: Category of usage (ai_generation/email_validation/lead_lookup/api_call).
        credits: Number of credits consumed.
        description: Human-readable description.
        user_id: User who triggered the usage.
        reference_id: Related entity identifier (campaign_id, contact_id, etc).

    Returns:
        The created CreditUsage record.
    """
    entry = CreditUsage(
        tenant_id=tenant_id,
        user_id=user_id,
        usage_type=usage_type,
        credits_used=credits,
        description=description,
        reference_id=reference_id,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)

    logger.info(
        "credit_usage_recorded",
        tenant_id=tenant_id,
        usage_type=usage_type,
        credits=credits,
    )
    return entry


def get_usage_summary(
    db: Session,
    tenant_id: int,
    days: int = 30,
) -> dict:
    """Get usage summary grouped by type.

    Args:
        db: Database session.
        tenant_id: Tenant scope.
        days: Number of days to look back.

    Returns:
        Dict with period, per-type breakdown, and total credits used.
    """
    cutoff = datetime.utcnow() - timedelta(days=days)
    q = db.query(
        CreditUsage.usage_type,
        func.sum(CreditUsage.credits_used).label("total"),
        func.count(CreditUsage.usage_id).label("count"),
    ).filter(
        CreditUsage.recorded_at >= cutoff,
        CreditUsage.is_archived == False,
    )
    q = tenant_filter(q, CreditUsage, tenant_id)
    rows = q.group_by(CreditUsage.usage_type).all()

    usage_list = [
        {
            "type": r.usage_type,
            "total_credits": float(r.total or 0),
            "count": r.count,
        }
        for r in rows
    ]

    return {
        "period_days": days,
        "usage": usage_list,
        "total_credits_used": sum(item["total_credits"] for item in usage_list),
    }


def get_usage_history(
    db: Session,
    tenant_id: int,
    usage_type: str = None,
    page: int = 1,
    page_size: int = 50,
) -> dict:
    """Get paginated credit usage history.

    Args:
        db: Database session.
        tenant_id: Tenant scope.
        usage_type: Optional filter by usage type.
        page: Page number (1-indexed).
        page_size: Items per page.

    Returns:
        Dict with items, total, page, page_size, and pages.
    """
    q = db.query(CreditUsage).filter(CreditUsage.is_archived == False)
    q = tenant_filter(q, CreditUsage, tenant_id)

    if usage_type:
        q = q.filter(CreditUsage.usage_type == usage_type)

    total = q.count()
    items = q.order_by(CreditUsage.recorded_at.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size).all()

    return {
        "items": [
            {
                "usage_id": item.usage_id,
                "usage_type": item.usage_type,
                "credits_used": float(item.credits_used),
                "description": item.description,
                "reference_id": item.reference_id,
                "recorded_at": item.recorded_at.isoformat() if item.recorded_at else None,
            }
            for item in items
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size,
    }
