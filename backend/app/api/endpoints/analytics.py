"""Analytics endpoints — team leaderboard, campaign comparison, revenue metrics."""
from datetime import datetime, date, timedelta
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, case
from typing import Optional
from pydantic import BaseModel

from app.db.base import get_db
from app.api.deps.auth import get_current_user, require_role
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
):
    """Per-user performance metrics for the team leaderboard."""
    cutoff = datetime.utcnow() - timedelta(days=days)

    users = db.query(User).filter(User.is_active == True, User.is_archived == False).all()
    leaderboard = []

    for user in users:
        # Emails sent (outreach events linked to campaigns)
        emails_sent = db.query(func.count(OutreachEvent.event_id)).filter(
            OutreachEvent.status == OutreachStatus.SENT,
            OutreachEvent.sent_at >= cutoff,
        ).scalar() or 0

        # Deals won
        deals_won = db.query(func.count(Deal.deal_id)).join(
            DealStage, Deal.stage_id == DealStage.stage_id
        ).filter(
            DealStage.is_won == True,
            Deal.is_archived == False,
            Deal.updated_at >= cutoff,
        ).scalar() or 0

        total_won_value = db.query(func.sum(Deal.value)).join(
            DealStage, Deal.stage_id == DealStage.stage_id
        ).filter(
            DealStage.is_won == True,
            Deal.is_archived == False,
            Deal.updated_at >= cutoff,
        ).scalar() or 0

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
):
    """Per-campaign metrics for comparison."""
    campaigns = db.query(Campaign).filter(
        Campaign.is_archived == False,
    ).order_by(Campaign.created_at.desc()).limit(20).all()

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
):
    """Revenue metrics: total won value, avg deal size, pipeline value, cost per lead, ROI."""
    cutoff = datetime.utcnow() - timedelta(days=days)

    # Won deals
    won_stage_ids = [s.stage_id for s in db.query(DealStage).filter(DealStage.is_won == True).all()]

    total_won_value = db.query(func.sum(Deal.value)).filter(
        Deal.stage_id.in_(won_stage_ids),
        Deal.is_archived == False,
        Deal.updated_at >= cutoff,
    ).scalar() or 0

    deals_won_count = db.query(func.count(Deal.deal_id)).filter(
        Deal.stage_id.in_(won_stage_ids),
        Deal.is_archived == False,
        Deal.updated_at >= cutoff,
    ).scalar() or 0

    avg_deal_size = float(total_won_value) / deals_won_count if deals_won_count > 0 else 0

    # Pipeline value (non-won, non-lost deals)
    lost_stage_ids = [s.stage_id for s in db.query(DealStage).filter(DealStage.is_lost == True).all()]
    excluded_ids = set(won_stage_ids + lost_stage_ids)

    pipeline_value = db.query(func.sum(Deal.value)).filter(
        ~Deal.stage_id.in_(excluded_ids) if excluded_ids else True,
        Deal.is_archived == False,
    ).scalar() or 0

    # Total deals
    total_deals = db.query(func.count(Deal.deal_id)).filter(
        Deal.is_archived == False,
        Deal.created_at >= cutoff,
    ).scalar() or 0

    # Win rate
    total_closed = deals_won_count + db.query(func.count(Deal.deal_id)).filter(
        Deal.stage_id.in_(lost_stage_ids),
        Deal.is_archived == False,
        Deal.updated_at >= cutoff,
    ).scalar()
    win_rate = (deals_won_count / total_closed * 100) if total_closed > 0 else 0

    # Cost tracking
    total_costs = 0
    try:
        from app.db.models.cost_tracking import CostEntry
        total_costs = db.query(func.sum(CostEntry.amount)).filter(
            CostEntry.entry_date >= cutoff.date(),
            CostEntry.is_archived == False,
        ).scalar() or 0
    except Exception:
        pass

    # Leads generated in period
    from app.db.models.lead import LeadDetails
    leads_generated = db.query(func.count(LeadDetails.lead_id)).filter(
        LeadDetails.created_at >= cutoff,
        LeadDetails.is_archived == False,
    ).scalar() or 0

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
    entry_date: str  # YYYY-MM-DD
    notes: Optional[str] = None


@router.post("/costs")
def create_cost_entry(
    body: CostEntryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN])),
):
    """Record a cost entry for ROI tracking."""
    from app.db.models.cost_tracking import CostEntry
    entry = CostEntry(
        category=body.category,
        amount=body.amount,
        entry_date=datetime.strptime(body.entry_date, "%Y-%m-%d").date(),
        notes=body.notes,
        user_id=current_user.user_id,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)

    return {
        "cost_id": entry.cost_id,
        "category": entry.category,
        "amount": float(entry.amount),
        "entry_date": str(entry.entry_date),
    }


@router.get("/costs")
def list_cost_entries(
    days: int = Query(90, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN])),
):
    """List cost entries."""
    from app.db.models.cost_tracking import CostEntry
    cutoff = (datetime.utcnow() - timedelta(days=days)).date()

    entries = db.query(CostEntry).filter(
        CostEntry.entry_date >= cutoff,
        CostEntry.is_archived == False,
    ).order_by(CostEntry.entry_date.desc()).all()

    return [
        {
            "cost_id": e.cost_id,
            "category": e.category,
            "amount": float(e.amount),
            "entry_date": str(e.entry_date),
            "notes": e.notes,
        }
        for e in entries
    ]
