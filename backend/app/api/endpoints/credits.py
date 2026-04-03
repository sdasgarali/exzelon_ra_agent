"""Credit and usage metering endpoints."""
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from app.db.base import get_db
from app.api.deps.auth import get_current_active_user, get_current_tenant_id
from app.db.query_helpers import tenant_filter
from app.db.models.user import User
from app.db.models.credit_usage import CreditUsage

router = APIRouter(prefix="/credits", tags=["Credits"])


@router.get("/usage")
def list_usage(
    usage_type: Optional[str] = None,
    from_date: Optional[str] = None,  # YYYY-MM-DD
    to_date: Optional[str] = None,  # YYYY-MM-DD
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """List credit usage entries with optional filters."""
    q = db.query(CreditUsage).filter(CreditUsage.is_archived == False)
    q = tenant_filter(q, CreditUsage, tenant_id)

    if usage_type:
        q = q.filter(CreditUsage.usage_type == usage_type)
    if from_date:
        try:
            dt = datetime.strptime(from_date, "%Y-%m-%d")
            q = q.filter(CreditUsage.recorded_at >= dt)
        except ValueError:
            pass
    if to_date:
        try:
            dt = datetime.strptime(to_date, "%Y-%m-%d") + timedelta(days=1)
            q = q.filter(CreditUsage.recorded_at < dt)
        except ValueError:
            pass

    total = q.count()
    items = q.order_by(desc(CreditUsage.recorded_at)).offset(
        (page - 1) * page_size
    ).limit(page_size).all()

    return {
        "items": [
            {
                "usage_id": u.usage_id,
                "tenant_id": u.tenant_id,
                "user_id": u.user_id,
                "usage_type": u.usage_type,
                "credits_used": u.credits_used,
                "description": u.description,
                "reference_id": u.reference_id,
                "recorded_at": u.recorded_at.isoformat() if u.recorded_at else None,
            }
            for u in items
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/summary")
def usage_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Usage summary by type for the current month."""
    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    q = db.query(
        CreditUsage.usage_type,
        func.sum(CreditUsage.credits_used).label("total_credits"),
        func.count(CreditUsage.usage_id).label("count"),
    ).filter(
        CreditUsage.is_archived == False,
        CreditUsage.recorded_at >= month_start,
    )
    q = tenant_filter(q, CreditUsage, tenant_id)
    rows = q.group_by(CreditUsage.usage_type).all()

    summary = []
    total_credits = 0.0
    for row in rows:
        credits = float(row.total_credits or 0)
        total_credits += credits
        summary.append({
            "usage_type": row.usage_type,
            "total_credits": round(credits, 2),
            "count": row.count,
        })

    return {
        "month": month_start.strftime("%Y-%m"),
        "total_credits_used": round(total_credits, 2),
        "by_type": summary,
    }


@router.get("/balance")
def credit_balance(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Get remaining credits vs plan limit for the current month."""
    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # Total used this month
    used_q = db.query(func.sum(CreditUsage.credits_used)).filter(
        CreditUsage.is_archived == False,
        CreditUsage.recorded_at >= month_start,
    )
    used_q = tenant_filter(used_q, CreditUsage, tenant_id)
    total_used = float(used_q.scalar() or 0)

    # Get tenant plan limit (if available)
    plan_limit = None
    try:
        from app.db.models.tenant import Tenant
        if tenant_id:
            tenant = db.query(Tenant).filter(Tenant.tenant_id == tenant_id).first()
            if tenant:
                # Credit limits could be stored in settings_json or as a plan attribute
                # For now, use plan-based defaults
                plan_limits = {
                    "starter": 1000,
                    "professional": 5000,
                    "enterprise": 50000,
                }
                plan_val = tenant.plan.value if hasattr(tenant.plan, 'value') else str(tenant.plan)
                plan_limit = plan_limits.get(plan_val, 1000)
    except Exception:
        pass

    remaining = (plan_limit - total_used) if plan_limit else None

    return {
        "month": month_start.strftime("%Y-%m"),
        "total_used": round(total_used, 2),
        "plan_limit": plan_limit,
        "remaining": round(remaining, 2) if remaining is not None else None,
        "utilization_percent": round(total_used / plan_limit * 100, 1) if plan_limit and plan_limit > 0 else None,
    }
