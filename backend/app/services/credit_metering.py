"""Credit usage tracking and metering."""
import structlog
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.db.models.credit_usage import CreditUsage
from app.db.query_helpers import tenant_filter

logger = structlog.get_logger()


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
