"""AI-powered deal pipeline forecasting."""
import structlog
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.db.models.deal import Deal, DealStage

logger = structlog.get_logger()


def generate_forecast(db: Session, tenant_id=None, months_ahead=3):
    """Generate revenue forecast based on historical deal data.

    Uses win rate, average deal value, and weighted pipeline to project
    monthly revenue for the next N months.
    """
    from app.db.query_helpers import tenant_filter

    # Historical win rate
    won_stages = db.query(DealStage).filter(DealStage.is_won == True).all()
    lost_stages = db.query(DealStage).filter(DealStage.is_lost == True).all()
    won_ids = [s.stage_id for s in won_stages]
    lost_ids = [s.stage_id for s in lost_stages]

    # Last 90 days metrics
    cutoff = datetime.utcnow() - timedelta(days=90)

    won_q = db.query(func.count(Deal.deal_id)).filter(
        Deal.stage_id.in_(won_ids) if won_ids else False,
        Deal.updated_at >= cutoff,
        Deal.is_archived == False,
    )
    won_q = tenant_filter(won_q, Deal, tenant_id)
    won_count = won_q.scalar() or 0

    lost_q = db.query(func.count(Deal.deal_id)).filter(
        Deal.stage_id.in_(lost_ids) if lost_ids else False,
        Deal.updated_at >= cutoff,
        Deal.is_archived == False,
    )
    lost_q = tenant_filter(lost_q, Deal, tenant_id)
    lost_count = lost_q.scalar() or 0

    total_closed = won_count + lost_count
    win_rate = (won_count / total_closed) if total_closed > 0 else 0.3  # default 30%

    # Average deal value
    avg_val_q = db.query(func.avg(Deal.value)).filter(
        Deal.stage_id.in_(won_ids) if won_ids else False,
        Deal.is_archived == False,
    )
    avg_val_q = tenant_filter(avg_val_q, Deal, tenant_id)
    avg_deal_value = float(avg_val_q.scalar() or 0)

    # Pipeline deals (not won/lost)
    excluded = set(won_ids + lost_ids)
    if excluded:
        pipeline_q = db.query(Deal).filter(
            ~Deal.stage_id.in_(excluded),
            Deal.is_archived == False,
        )
    else:
        pipeline_q = db.query(Deal).filter(Deal.is_archived == False)
    pipeline_q = tenant_filter(pipeline_q, Deal, tenant_id)
    pipeline_deals = pipeline_q.all()

    # Weighted pipeline value
    weighted_pipeline = sum(
        float(d.value or 0) * float(d.probability or 50) / 100
        for d in pipeline_deals
    )

    # Monthly forecast
    monthly_forecasts = []
    for i in range(months_ahead):
        month_start = datetime.utcnow() + timedelta(days=30 * i)
        # Simple linear projection: weighted pipeline / months_ahead with decay
        if i == 0:
            projected = weighted_pipeline / max(months_ahead, 1)
        else:
            projected = weighted_pipeline / max(months_ahead, 1) * (1 - 0.1 * i)

        monthly_forecasts.append({
            "month": month_start.strftime("%Y-%m"),
            "projected_revenue": round(max(projected, 0), 2),
            "confidence": max(50 - i * 10, 20),
        })

    return {
        "win_rate": round(win_rate * 100, 1),
        "avg_deal_value": round(avg_deal_value, 2),
        "pipeline_deals_count": len(pipeline_deals),
        "weighted_pipeline_value": round(weighted_pipeline, 2),
        "total_pipeline_value": round(
            sum(float(d.value or 0) for d in pipeline_deals), 2
        ),
        "monthly_forecasts": monthly_forecasts,
    }
