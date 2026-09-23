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
    """Remaining credits for the current month, split by source.

    Reads the balance row rather than re-summing the ledger, so this agrees exactly
    with what the 402 gate will decide. Allowance and top-ups are reported separately
    because they behave differently: the allowance resets on the 1st, top-ups never
    expire and are only drawn on once the allowance is gone.
    """
    from app.services.credit_metering import available_credits

    if tenant_id is None:
        # Super admin: not metered, and has no single tenant's balance to report.
        return {"metered": False, "message": "Super admin usage is not metered."}

    from app.services.send_quota import quota_status

    info = available_credits(db, tenant_id)
    plan_allowance = info.get("plan_allowance") or 0
    spent = info.get("period_spent") or 0

    return {
        "month": (info.get("period_start") or "")[:7],
        "plan_allowance": plan_allowance,
        "allowance_remaining": info["allowance"],
        "topup_remaining": info["topup"],
        "total_remaining": info["total"],
        "used_this_month": spent,
        "utilization_percent": (
            round(spent / plan_allowance * 100, 1) if plan_allowance > 0 else None
        ),
        # The second meter. Returned alongside credits so the usage screen can show
        # both without a second round-trip — they are separate budgets and running
        # out of one says nothing about the other.
        "sends": quota_status(db, tenant_id),
        "metered": True,
    }


@router.get("/price-list")
def credit_price_list(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """What each metered action costs, so the UI never hardcodes a number."""
    from app.core.credit_costs import CREDITS_PER_FULL_CONTACT, price_list

    return {
        "actions": price_list(db),
        "credits_per_full_contact": CREDITS_PER_FULL_CONTACT,
        "note": (
            "Email sends and warmup are free — they are governed by the monthly send "
            "quota, not credits."
        ),
    }
