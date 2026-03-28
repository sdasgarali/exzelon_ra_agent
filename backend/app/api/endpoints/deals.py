"""CRM Deal Pipeline API endpoints."""
import json
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.api.deps.database import get_db
from app.api.deps.auth import get_current_active_user, require_role, get_current_tenant_id
from app.db.models.user import User, UserRole
from app.db.models.deal import Deal, DealStage, DealActivity
from app.db.models.contact import ContactDetails
from app.db.models.client import ClientInfo
from app.db.query_helpers import tenant_filter

router = APIRouter(prefix="/deals", tags=["deals"])


class DealCreate(BaseModel):
    name: str = Field(..., max_length=255)
    stage_id: int
    contact_id: Optional[int] = None
    client_id: Optional[int] = None
    campaign_id: Optional[int] = None
    value: float = 0
    probability: int = 0
    expected_close_date: Optional[str] = None
    notes: Optional[str] = None

class DealUpdate(BaseModel):
    name: Optional[str] = None
    stage_id: Optional[int] = None
    contact_id: Optional[int] = None
    client_id: Optional[int] = None
    value: Optional[float] = None
    probability: Optional[int] = None
    expected_close_date: Optional[str] = None
    notes: Optional[str] = None

class StageCreate(BaseModel):
    name: str = Field(..., max_length=100)
    stage_order: int
    color: str = "#6b7280"
    is_won: bool = False
    is_lost: bool = False

class StageUpdate(BaseModel):
    name: Optional[str] = None
    stage_order: Optional[int] = None
    color: Optional[str] = None

class ActivityCreate(BaseModel):
    activity_type: str  # note/stage_change/email_sent/email_received/call
    description: Optional[str] = None
    metadata_json: Optional[str] = None


def _deal_to_dict(d: Deal, db: Session = None) -> dict:
    result = {
        "deal_id": d.deal_id,
        "name": d.name,
        "stage_id": d.stage_id,
        "contact_id": d.contact_id,
        "client_id": d.client_id,
        "campaign_id": d.campaign_id,
        "value": float(d.value) if d.value else 0,
        "probability": d.probability,
        "expected_close_date": str(d.expected_close_date) if d.expected_close_date else None,
        "owner_id": d.owner_id,
        "notes": d.notes,
        "is_auto_created": getattr(d, "is_auto_created", False),
        "probability_manual": getattr(d, "probability_manual", False),
        "won_at": d.won_at.isoformat() if d.won_at else None,
        "lost_at": d.lost_at.isoformat() if d.lost_at else None,
        "lost_reason": d.lost_reason,
        "created_at": d.created_at.isoformat() if d.created_at else None,
        "updated_at": d.updated_at.isoformat() if d.updated_at else None,
    }

    if db and d.contact_id:
        contact = db.query(ContactDetails).filter(
            ContactDetails.contact_id == d.contact_id
        ).first()
        if contact:
            result["contact_name"] = f"{contact.first_name or ''} {contact.last_name or ''}".strip()
            result["contact_email"] = contact.email

    if db and d.client_id:
        client = db.query(ClientInfo).filter(
            ClientInfo.client_id == d.client_id
        ).first()
        if client:
            result["client_name"] = client.name

    if db:
        stage = db.query(DealStage).filter(DealStage.stage_id == d.stage_id).first()
        if stage:
            result["stage_name"] = stage.name
            result["stage_color"] = stage.color

    return result


# ─── Stages ────────────────────────────────────────────────────────

@router.get("/stages")
def list_stages(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    query = db.query(DealStage).filter(
        DealStage.is_archived == False
    )
    query = tenant_filter(query, DealStage, tenant_id)
    stages = query.order_by(DealStage.stage_order).all()
    return [
        {
            "stage_id": s.stage_id,
            "name": s.name,
            "stage_order": s.stage_order,
            "color": s.color,
            "is_won": s.is_won,
            "is_lost": s.is_lost,
        }
        for s in stages
    ]


@router.post("/stages")
def create_stage(
    data: StageCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([UserRole.ADMIN])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    stage = DealStage(
        tenant_id=tenant_id or 1,
        name=data.name,
        stage_order=data.stage_order,
        color=data.color,
        is_won=data.is_won,
        is_lost=data.is_lost,
    )
    db.add(stage)
    db.commit()
    db.refresh(stage)
    return {"stage_id": stage.stage_id, "name": stage.name}


@router.put("/stages/{stage_id}")
def update_stage(
    stage_id: int,
    data: StageUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([UserRole.ADMIN])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    stage = db.query(DealStage).filter(DealStage.stage_id == stage_id).first()
    if not stage:
        raise HTTPException(status_code=404, detail="Stage not found")
    if tenant_id is not None and stage.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(stage, field, value)
    db.commit()
    return {"message": "Stage updated"}


# ─── Deals CRUD ────────────────────────────────────────────────────

@router.get("")
def list_deals(
    stage_id: Optional[int] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    query = db.query(Deal).filter(Deal.is_archived == False)
    query = tenant_filter(query, Deal, tenant_id)
    if stage_id:
        query = query.filter(Deal.stage_id == stage_id)
    total = query.count()
    deals = query.order_by(Deal.created_at.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size).all()
    return {
        "items": [_deal_to_dict(d, db) for d in deals],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/pipeline")
def pipeline_view(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Get deals grouped by stage for Kanban board."""
    stage_query = db.query(DealStage).filter(
        DealStage.is_archived == False
    )
    stage_query = tenant_filter(stage_query, DealStage, tenant_id)
    stages = stage_query.order_by(DealStage.stage_order).all()

    result = []
    for stage in stages:
        deal_query = db.query(Deal).filter(
            Deal.stage_id == stage.stage_id,
            Deal.is_archived == False,
        )
        deal_query = tenant_filter(deal_query, Deal, tenant_id)
        deals = deal_query.order_by(Deal.created_at.desc()).all()

        result.append({
            "stage_id": stage.stage_id,
            "name": stage.name,
            "color": stage.color,
            "stage_order": stage.stage_order,
            "is_won": stage.is_won,
            "is_lost": stage.is_lost,
            "deals": [_deal_to_dict(d, db) for d in deals],
            "total_value": sum(float(d.value or 0) for d in deals),
            "count": len(deals),
        })

    return result


@router.get("/stats")
def deal_stats(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Pipeline summary statistics."""
    deal_base = db.query(Deal).filter(Deal.is_archived == False)
    deal_base = tenant_filter(deal_base, Deal, tenant_id)
    total_deals = deal_base.count()

    value_query = db.query(func.sum(Deal.value)).filter(Deal.is_archived == False)
    value_query = tenant_filter(value_query, Deal, tenant_id)
    total_value = value_query.scalar() or 0

    won_stage_query = db.query(DealStage.stage_id).filter(DealStage.is_won == True)
    won_stage_query = tenant_filter(won_stage_query, DealStage, tenant_id)
    won_stages = won_stage_query.all()
    won_ids = [s[0] for s in won_stages]

    lost_stage_query = db.query(DealStage.stage_id).filter(DealStage.is_lost == True)
    lost_stage_query = tenant_filter(lost_stage_query, DealStage, tenant_id)
    lost_stages = lost_stage_query.all()
    lost_ids = [s[0] for s in lost_stages]

    if won_ids:
        won_query = db.query(Deal).filter(
            Deal.stage_id.in_(won_ids), Deal.is_archived == False
        )
        won_query = tenant_filter(won_query, Deal, tenant_id)
        won_count = won_query.count()
    else:
        won_count = 0

    if lost_ids:
        lost_query = db.query(Deal).filter(
            Deal.stage_id.in_(lost_ids), Deal.is_archived == False
        )
        lost_query = tenant_filter(lost_query, Deal, tenant_id)
        lost_count = lost_query.count()
    else:
        lost_count = 0

    closed = won_count + lost_count
    win_rate = round(won_count / closed * 100, 1) if closed > 0 else 0

    if won_ids:
        won_val_query = db.query(func.sum(Deal.value)).filter(
            Deal.stage_id.in_(won_ids), Deal.is_archived == False
        )
        won_val_query = tenant_filter(won_val_query, Deal, tenant_id)
        won_value = won_val_query.scalar() or 0
    else:
        won_value = 0

    avg_deal = round(float(won_value) / won_count, 2) if won_count > 0 else 0

    return {
        "total_deals": total_deals,
        "total_pipeline_value": float(total_value),
        "won_count": won_count,
        "lost_count": lost_count,
        "win_rate": win_rate,
        "avg_deal_size": avg_deal,
        "won_value": float(won_value),
    }


@router.post("")
def create_deal(
    data: DealCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    from datetime import date as date_type
    deal = Deal(
        tenant_id=tenant_id or 1,
        name=data.name,
        stage_id=data.stage_id,
        contact_id=data.contact_id,
        client_id=data.client_id,
        campaign_id=data.campaign_id,
        value=data.value,
        probability=data.probability,
        expected_close_date=date_type.fromisoformat(data.expected_close_date) if data.expected_close_date else None,
        owner_id=user.user_id,
        notes=data.notes,
    )
    db.add(deal)
    db.flush()

    # Mark manual probability if user set it
    if data.probability and data.probability > 0:
        deal.probability_manual = True

    # Log creation activity
    db.add(DealActivity(
        deal_id=deal.deal_id,
        activity_type="note",
        description="Deal created",
        created_by=user.user_id,
    ))

    db.commit()
    db.refresh(deal)

    # Fire webhook
    try:
        from app.services.webhook_dispatcher import dispatch_webhook_event
        dispatch_webhook_event("deal.created", {
            "deal_id": deal.deal_id, "name": deal.name,
            "stage_id": deal.stage_id, "value": float(deal.value),
        }, db)
    except Exception:
        pass

    return _deal_to_dict(deal, db)


@router.get("/{deal_id}")
def get_deal(
    deal_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    deal = db.query(Deal).filter(Deal.deal_id == deal_id).first()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    if tenant_id is not None and deal.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied")

    result = _deal_to_dict(deal, db)

    # Include activities
    activities = db.query(DealActivity).filter(
        DealActivity.deal_id == deal_id
    ).order_by(DealActivity.created_at.desc()).limit(50).all()

    result["activities"] = [
        {
            "activity_id": a.activity_id,
            "activity_type": a.activity_type,
            "description": a.description,
            "metadata_json": a.metadata_json,
            "created_by": a.created_by,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in activities
    ]
    return result


@router.put("/{deal_id}")
def update_deal(
    deal_id: int,
    data: DealUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    deal = db.query(Deal).filter(Deal.deal_id == deal_id).first()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    if tenant_id is not None and deal.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied")

    old_stage = deal.stage_id

    if data.name is not None:
        deal.name = data.name
    if data.contact_id is not None:
        deal.contact_id = data.contact_id
    if data.client_id is not None:
        deal.client_id = data.client_id
    if data.value is not None:
        deal.value = data.value
    if data.probability is not None:
        deal.probability = data.probability
        deal.probability_manual = True  # User explicitly set probability
    if data.expected_close_date is not None:
        from datetime import date as date_type
        deal.expected_close_date = date_type.fromisoformat(data.expected_close_date)
    if data.notes is not None:
        deal.notes = data.notes

    if data.stage_id is not None and data.stage_id != old_stage:
        deal.stage_id = data.stage_id
        new_stage = db.query(DealStage).filter(DealStage.stage_id == data.stage_id).first()
        old_stage_obj = db.query(DealStage).filter(DealStage.stage_id == old_stage).first()

        if new_stage and new_stage.is_won:
            deal.won_at = datetime.utcnow()
        elif new_stage and new_stage.is_lost:
            deal.lost_at = datetime.utcnow()

        db.add(DealActivity(
            deal_id=deal_id,
            activity_type="stage_change",
            description=f"Moved from {old_stage_obj.name if old_stage_obj else 'Unknown'} to {new_stage.name if new_stage else 'Unknown'}",
            created_by=user.user_id,
        ))

        # Fire webhook for stage change / won / lost
        try:
            from app.services.webhook_dispatcher import dispatch_webhook_event
            event_type = "deal.stage_changed"
            if new_stage and new_stage.is_won:
                event_type = "deal.won"
            elif new_stage and new_stage.is_lost:
                event_type = "deal.lost"
            dispatch_webhook_event(event_type, {
                "deal_id": deal_id, "name": deal.name,
                "from_stage": old_stage_obj.name if old_stage_obj else "Unknown",
                "to_stage": new_stage.name if new_stage else "Unknown",
                "value": float(deal.value),
            }, db)
        except Exception:
            pass

    db.commit()
    db.refresh(deal)
    return _deal_to_dict(deal, db)


@router.delete("/{deal_id}")
def archive_deal(
    deal_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([UserRole.ADMIN])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    deal = db.query(Deal).filter(Deal.deal_id == deal_id).first()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    if tenant_id is not None and deal.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied")
    deal.is_archived = True
    db.commit()
    return {"message": "Deal archived"}


# ─── Stale & Forecast ─────────────────────────────────────────────

@router.get("/stale")
def stale_deals(
    days: int = Query(7, ge=1, le=90),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Get deals with no activity in the last N days."""
    from app.services.deal_automation import detect_stale_deals
    return detect_stale_deals(db, days_threshold=days, tenant_id=tenant_id)


@router.get("/forecast")
def pipeline_forecast(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Weighted pipeline forecast: sum of (value * probability / 100)."""
    from app.services.deal_automation import calculate_pipeline_forecast
    return calculate_pipeline_forecast(db, tenant_id=tenant_id)


# ─── Contact/Client Search (for deal creation pickers) ────────────

@router.get("/search/contacts")
def search_contacts_for_deal(
    q: str = Query("", min_length=0, max_length=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Search contacts for the deal creation picker."""
    query = db.query(ContactDetails).filter(ContactDetails.is_archived == False)
    query = tenant_filter(query, ContactDetails, tenant_id)
    if q:
        search = f"%{q}%"
        query = query.filter(
            (ContactDetails.first_name.ilike(search)) |
            (ContactDetails.last_name.ilike(search)) |
            (ContactDetails.email.ilike(search)) |
            (ContactDetails.client_name.ilike(search))
        )
    contacts = query.order_by(ContactDetails.first_name).limit(20).all()
    return [
        {
            "contact_id": c.contact_id,
            "name": f"{c.first_name or ''} {c.last_name or ''}".strip(),
            "email": c.email,
            "company": c.client_name,
            "title": c.title,
        }
        for c in contacts
    ]


@router.get("/search/clients")
def search_clients_for_deal(
    q: str = Query("", min_length=0, max_length=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Search clients/companies for the deal creation picker."""
    query = db.query(ClientInfo).filter(ClientInfo.is_archived == False)
    query = tenant_filter(query, ClientInfo, tenant_id)
    if q:
        search = f"%{q}%"
        query = query.filter(ClientInfo.name.ilike(search))
    clients = query.order_by(ClientInfo.name).limit(20).all()
    return [
        {"client_id": c.client_id, "name": c.name}
        for c in clients
    ]


# ─── Activities ────────────────────────────────────────────────────

@router.post("/{deal_id}/activities")
def add_activity(
    deal_id: int,
    data: ActivityCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    deal = db.query(Deal).filter(Deal.deal_id == deal_id).first()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    if tenant_id is not None and deal.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied")

    activity = DealActivity(
        deal_id=deal_id,
        activity_type=data.activity_type,
        description=data.description,
        metadata_json=data.metadata_json,
        created_by=user.user_id,
    )
    db.add(activity)
    db.commit()
    return {"message": "Activity added", "activity_id": activity.activity_id}
