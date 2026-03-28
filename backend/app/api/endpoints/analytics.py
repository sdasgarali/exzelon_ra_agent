"""Analytics endpoints — team leaderboard, campaign comparison, revenue metrics."""
from datetime import datetime, date, timedelta
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, case
from typing import Optional
from pydantic import BaseModel, field_validator

from app.db.base import get_db
from app.api.deps.auth import get_current_user, require_role, get_current_tenant_id
from app.db.query_helpers import tenant_filter
from app.db.models.user import User, UserRole
from app.db.models.outreach import OutreachEvent, OutreachStatus
from app.db.models.campaign import Campaign, CampaignContact, CampaignContactStatus
from app.db.models.deal import Deal, DealStage
from app.db.models.contact import ContactDetails

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/team-leaderboard")
def team_leaderboard(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Per-user performance metrics for the team leaderboard."""
    cutoff = datetime.utcnow() - timedelta(days=days)

    user_query = db.query(User).filter(User.is_active == True, User.is_archived == False)
    user_query = tenant_filter(user_query, User, tenant_id)
    users = user_query.all()
    leaderboard = []

    for user in users:
        # Emails sent (outreach events linked to campaigns)
        sent_query = db.query(func.count(OutreachEvent.event_id)).filter(
            OutreachEvent.status == OutreachStatus.SENT,
            OutreachEvent.sent_at >= cutoff,
        )
        sent_query = tenant_filter(sent_query, OutreachEvent, tenant_id)
        emails_sent = sent_query.scalar() or 0

        # Deals won
        won_query = db.query(func.count(Deal.deal_id)).join(
            DealStage, Deal.stage_id == DealStage.stage_id
        ).filter(
            DealStage.is_won == True,
            Deal.is_archived == False,
            Deal.updated_at >= cutoff,
        )
        won_query = tenant_filter(won_query, Deal, tenant_id)
        deals_won = won_query.scalar() or 0

        val_query = db.query(func.sum(Deal.value)).join(
            DealStage, Deal.stage_id == DealStage.stage_id
        ).filter(
            DealStage.is_won == True,
            Deal.is_archived == False,
            Deal.updated_at >= cutoff,
        )
        val_query = tenant_filter(val_query, Deal, tenant_id)
        total_won_value = val_query.scalar() or 0

        leaderboard.append({
            "user_id": user.user_id,
            "name": user.full_name or user.email,
            "role": user.role.value if user.role else "viewer",
            "emails_sent": emails_sent,
            "deals_won": deals_won,
            "total_won_value": float(total_won_value),
        })

    # Sort by deals_won descending
    leaderboard.sort(key=lambda x: x["deals_won"], reverse=True)

    return {"period_days": days, "leaderboard": leaderboard}


@router.get("/campaign-comparison")
def campaign_comparison(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.OPERATOR])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Per-campaign metrics for comparison."""
    camp_query = db.query(Campaign).filter(
        Campaign.is_archived == False,
    )
    camp_query = tenant_filter(camp_query, Campaign, tenant_id)
    campaigns = camp_query.order_by(Campaign.created_at.desc()).limit(20).all()

    comparisons = []
    for campaign in campaigns:
        cid = campaign.campaign_id

        sent = db.query(func.count(OutreachEvent.event_id)).filter(
            OutreachEvent.campaign_id == cid,
            OutreachEvent.status == OutreachStatus.SENT,
        ).scalar() or 0

        replied = db.query(func.count(CampaignContact.id)).filter(
            CampaignContact.campaign_id == cid,
            CampaignContact.status == CampaignContactStatus.REPLIED,
        ).scalar() or 0

        bounced = db.query(func.count(CampaignContact.id)).filter(
            CampaignContact.campaign_id == cid,
            CampaignContact.status == CampaignContactStatus.BOUNCED,
        ).scalar() or 0

        total_contacts = db.query(func.count(CampaignContact.id)).filter(
            CampaignContact.campaign_id == cid,
        ).scalar() or 0

        reply_rate = (replied / sent * 100) if sent > 0 else 0
        bounce_rate = (bounced / sent * 100) if sent > 0 else 0

        comparisons.append({
            "campaign_id": cid,
            "name": campaign.name,
            "status": campaign.status.value if campaign.status else "draft",
            "total_contacts": total_contacts,
            "sent": sent,
            "replied": replied,
            "bounced": bounced,
            "reply_rate": round(reply_rate, 1),
            "bounce_rate": round(bounce_rate, 1),
            "created_at": campaign.created_at.isoformat() if campaign.created_at else None,
        })

    return {"campaigns": comparisons}


@router.get("/revenue")
def revenue_analytics(
    days: int = Query(90, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Revenue metrics: total won value, avg deal size, pipeline value, cost per lead, ROI."""
    cutoff = datetime.utcnow() - timedelta(days=days)

    # Won deals
    won_stage_ids = [s.stage_id for s in db.query(DealStage).filter(DealStage.is_won == True).all()]

    won_val_query = db.query(func.sum(Deal.value)).filter(
        Deal.stage_id.in_(won_stage_ids),
        Deal.is_archived == False,
        Deal.updated_at >= cutoff,
    )
    won_val_query = tenant_filter(won_val_query, Deal, tenant_id)
    total_won_value = won_val_query.scalar() or 0

    won_count_query = db.query(func.count(Deal.deal_id)).filter(
        Deal.stage_id.in_(won_stage_ids),
        Deal.is_archived == False,
        Deal.updated_at >= cutoff,
    )
    won_count_query = tenant_filter(won_count_query, Deal, tenant_id)
    deals_won_count = won_count_query.scalar() or 0

    avg_deal_size = float(total_won_value) / deals_won_count if deals_won_count > 0 else 0

    # Pipeline value (non-won, non-lost deals)
    lost_stage_ids = [s.stage_id for s in db.query(DealStage).filter(DealStage.is_lost == True).all()]
    excluded_ids = set(won_stage_ids + lost_stage_ids)

    pipeline_query = db.query(func.sum(Deal.value)).filter(
        ~Deal.stage_id.in_(excluded_ids) if excluded_ids else True,
        Deal.is_archived == False,
    )
    pipeline_query = tenant_filter(pipeline_query, Deal, tenant_id)
    pipeline_value = pipeline_query.scalar() or 0

    # Total deals
    total_deals_query = db.query(func.count(Deal.deal_id)).filter(
        Deal.is_archived == False,
        Deal.created_at >= cutoff,
    )
    total_deals_query = tenant_filter(total_deals_query, Deal, tenant_id)
    total_deals = total_deals_query.scalar() or 0

    # Win rate
    lost_count_query = db.query(func.count(Deal.deal_id)).filter(
        Deal.stage_id.in_(lost_stage_ids),
        Deal.is_archived == False,
        Deal.updated_at >= cutoff,
    )
    lost_count_query = tenant_filter(lost_count_query, Deal, tenant_id)
    total_closed = deals_won_count + lost_count_query.scalar()
    win_rate = (deals_won_count / total_closed * 100) if total_closed > 0 else 0

    # Cost tracking
    total_costs = 0
    try:
        from app.db.models.cost_tracking import CostEntry
        cost_query = db.query(func.sum(CostEntry.amount)).filter(
            CostEntry.entry_date >= cutoff.date(),
            CostEntry.is_archived == False,
        )
        cost_query = tenant_filter(cost_query, CostEntry, tenant_id)
        total_costs = cost_query.scalar() or 0
    except Exception:
        pass

    # Leads generated in period
    from app.db.models.lead import LeadDetails
    leads_query = db.query(func.count(LeadDetails.lead_id)).filter(
        LeadDetails.created_at >= cutoff,
        LeadDetails.is_archived == False,
    )
    leads_query = tenant_filter(leads_query, LeadDetails, tenant_id)
    leads_generated = leads_query.scalar() or 0

    cost_per_lead = float(total_costs) / leads_generated if leads_generated > 0 else 0
    roi = ((float(total_won_value) - float(total_costs)) / float(total_costs) * 100) if float(total_costs) > 0 else 0

    return {
        "period_days": days,
        "total_won_value": float(total_won_value),
        "deals_won": deals_won_count,
        "avg_deal_size": round(avg_deal_size, 2),
        "pipeline_value": float(pipeline_value),
        "total_deals": total_deals,
        "win_rate": round(win_rate, 1),
        "leads_generated": leads_generated,
        "total_costs": float(total_costs),
        "cost_per_lead": round(cost_per_lead, 2),
        "roi_percent": round(roi, 1),
    }


class CostEntryCreate(BaseModel):
    category: str
    amount: float
    entry_date: Optional[str] = None  # YYYY-MM-DD
    date: Optional[str] = None  # Alias for entry_date (frontend compat)
    notes: Optional[str] = None
    source_adapter: Optional[str] = None

    @field_validator("entry_date", mode="before")
    @classmethod
    def resolve_date(cls, v, info):
        """Accept entry_date or fall back to 'date' field."""
        if v:
            return v
        # Will be resolved in the endpoint from 'date' field
        return v


class CostEntryUpdate(BaseModel):
    category: Optional[str] = None
    amount: Optional[float] = None
    entry_date: Optional[str] = None
    date: Optional[str] = None
    notes: Optional[str] = None
    source_adapter: Optional[str] = None


@router.post("/costs")
def create_cost_entry(
    body: CostEntryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Record a cost entry for ROI tracking."""
    from app.db.models.cost_tracking import CostEntry

    # Resolve date field: prefer entry_date, fall back to date
    date_str = body.entry_date or body.date
    if not date_str:
        raise HTTPException(status_code=422, detail="entry_date or date is required")

    entry = CostEntry(
        category=body.category,
        amount=body.amount,
        entry_date=datetime.strptime(date_str, "%Y-%m-%d").date(),
        notes=body.notes,
        user_id=current_user.user_id,
        source_adapter=body.source_adapter,
        is_automated=False,
        tenant_id=tenant_id or 1,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)

    return {
        "cost_id": entry.cost_id,
        "category": entry.category,
        "amount": float(entry.amount),
        "entry_date": str(entry.entry_date),
        "date": str(entry.entry_date),
        "source_adapter": entry.source_adapter,
        "is_automated": entry.is_automated,
    }


@router.get("/costs")
def list_cost_entries(
    days: int = Query(90, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """List cost entries."""
    from app.db.models.cost_tracking import CostEntry
    cutoff = (datetime.utcnow() - timedelta(days=days)).date()

    cost_query = db.query(CostEntry).filter(
        CostEntry.entry_date >= cutoff,
        CostEntry.is_archived == False,
    )
    cost_query = tenant_filter(cost_query, CostEntry, tenant_id)
    entries = cost_query.order_by(CostEntry.entry_date.desc()).all()

    return [
        {
            "cost_id": e.cost_id,
            "category": e.category,
            "amount": float(e.amount),
            "entry_date": str(e.entry_date),
            "date": str(e.entry_date),
            "notes": e.notes,
            "source_adapter": e.source_adapter,
            "is_automated": e.is_automated or False,
            "api_calls_count": e.api_calls_count,
            "results_count": e.results_count,
        }
        for e in entries
    ]


@router.put("/costs/{cost_id}")
def update_cost_entry(
    cost_id: int,
    body: CostEntryUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Update a cost entry."""
    from app.db.models.cost_tracking import CostEntry
    entry_query = db.query(CostEntry).filter(CostEntry.cost_id == cost_id, CostEntry.is_archived == False)
    entry_query = tenant_filter(entry_query, CostEntry, tenant_id)
    entry = entry_query.first()
    if not entry:
        raise HTTPException(status_code=404, detail="Cost entry not found")

    if body.category is not None:
        entry.category = body.category
    if body.amount is not None:
        entry.amount = body.amount

    date_str = body.entry_date or body.date
    if date_str:
        entry.entry_date = datetime.strptime(date_str, "%Y-%m-%d").date()

    if body.notes is not None:
        entry.notes = body.notes
    if body.source_adapter is not None:
        entry.source_adapter = body.source_adapter

    db.commit()
    db.refresh(entry)

    return {
        "cost_id": entry.cost_id,
        "category": entry.category,
        "amount": float(entry.amount),
        "entry_date": str(entry.entry_date),
        "date": str(entry.entry_date),
        "notes": entry.notes,
        "source_adapter": entry.source_adapter,
        "is_automated": entry.is_automated or False,
    }


@router.delete("/costs/{cost_id}")
def delete_cost_entry(
    cost_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Soft-delete a cost entry."""
    from app.db.models.cost_tracking import CostEntry
    entry_query = db.query(CostEntry).filter(CostEntry.cost_id == cost_id, CostEntry.is_archived == False)
    entry_query = tenant_filter(entry_query, CostEntry, tenant_id)
    entry = entry_query.first()
    if not entry:
        raise HTTPException(status_code=404, detail="Cost entry not found")

    entry.is_archived = True
    db.commit()

    return {"ok": True, "cost_id": cost_id}


@router.get("/costs/per-source")
def costs_per_source(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Cost breakdown grouped by source adapter."""
    from app.db.models.cost_tracking import CostEntry
    cutoff = (datetime.utcnow() - timedelta(days=days)).date()

    source_query = db.query(
        CostEntry.source_adapter,
        func.sum(CostEntry.amount).label("total_cost"),
        func.sum(CostEntry.api_calls_count).label("total_api_calls"),
        func.sum(CostEntry.results_count).label("total_results"),
        func.count(CostEntry.cost_id).label("entry_count"),
    ).filter(
        CostEntry.entry_date >= cutoff,
        CostEntry.is_archived == False,
    )
    source_query = tenant_filter(source_query, CostEntry, tenant_id)
    rows = source_query.group_by(CostEntry.source_adapter).all()

    sources = []
    for row in rows:
        total_cost = float(row.total_cost or 0)
        total_results = int(row.total_results or 0)
        cost_per_lead = total_cost / total_results if total_results > 0 else 0
        sources.append({
            "source": row.source_adapter or "manual",
            "total_cost": round(total_cost, 2),
            "total_api_calls": int(row.total_api_calls or 0),
            "total_results": total_results,
            "entry_count": row.entry_count,
            "cost_per_lead": round(cost_per_lead, 4),
        })

    # Sort by total_cost descending
    sources.sort(key=lambda x: x["total_cost"], reverse=True)

    return {"period_days": days, "sources": sources}


@router.get("/costs/daily-trend")
def costs_daily_trend(
    days: int = Query(30, ge=1, le=90),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Daily cost totals for trend chart."""
    from app.db.models.cost_tracking import CostEntry
    cutoff = (datetime.utcnow() - timedelta(days=days)).date()

    trend_query = db.query(
        CostEntry.entry_date,
        func.sum(CostEntry.amount).label("total"),
        func.sum(CostEntry.results_count).label("results"),
    ).filter(
        CostEntry.entry_date >= cutoff,
        CostEntry.is_archived == False,
    )
    trend_query = tenant_filter(trend_query, CostEntry, tenant_id)
    rows = trend_query.group_by(CostEntry.entry_date).order_by(CostEntry.entry_date).all()

    return {
        "period_days": days,
        "trend": [
            {
                "date": str(row.entry_date),
                "total": round(float(row.total or 0), 2),
                "results": int(row.results or 0),
            }
            for row in rows
        ],
    }


@router.get("/costs/budget-status")
def budget_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Current month cost utilization per source vs configured budgets."""
    from app.db.models.cost_tracking import CostEntry
    from app.services.cost_tracker import get_budget_status as _get_budget_status

    return _get_budget_status(db, tenant_id=tenant_id)
