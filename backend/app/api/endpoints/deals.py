"""CRM Deal Pipeline API endpoints."""
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.api.deps.database import get_db
from app.api.deps.auth import get_current_active_user, require_role, get_current_tenant_id, effective_base_role
from app.db.models.user import User, UserRole
from app.db.models.deal import Deal, DealStage, DealActivity
from app.db.models.deal import DealCandidate
from app.db.models.contact import ContactDetails
from app.db.models.client import ClientInfo
from app.db.models.lead import LeadDetails
from app.db.models.outreach import OutreachEvent
from app.db.models.inbox_message import InboxMessage
from app.db.query_helpers import tenant_filter, SIZE_OPERATORS, size_operator_clause

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


CANDIDATE_STATUSES = ["submitted", "reviewed", "sent_to_client", "placed", "rejected"]


class CandidateCreate(BaseModel):
    name: str = Field(..., max_length=255)
    email: Optional[str] = None
    phone: Optional[str] = None
    linkedin_url: Optional[str] = None
    resume_url: Optional[str] = None
    status: str = "submitted"
    notes: Optional[str] = None


class CandidateUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    linkedin_url: Optional[str] = None
    resume_url: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None


def _candidate_to_dict(c: DealCandidate, users_by_id: Optional[dict] = None) -> dict:
    return {
        "candidate_id": c.candidate_id,
        "deal_id": c.deal_id,
        "name": c.name,
        "email": c.email,
        "phone": c.phone,
        "linkedin_url": c.linkedin_url,
        "resume_url": c.resume_url,
        "status": c.status,
        "notes": c.notes,
        "submitted_by": _user_ref(None, c.submitted_by_user_id, users_by_id),
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }


def _initials(full_name: Optional[str]) -> str:
    """First+last initials from a name, e.g. 'Ricky Ponting' -> 'RP'."""
    if not full_name:
        return "?"
    parts = [p for p in full_name.strip().split() if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def _user_ref(db: Optional[Session], user_id: Optional[int], users_by_id: Optional[dict] = None) -> Optional[dict]:
    """Resolve a user id to {id, name, initials}. Uses a cache dict when provided."""
    if not user_id:
        return None
    user = None
    if users_by_id is not None:
        user = users_by_id.get(user_id)
    if user is None and db is not None:
        user = db.query(User).filter(User.user_id == user_id).first()
    if user is None:
        return {"id": user_id, "name": None, "initials": "?"}
    name = user.full_name or user.email
    return {"id": user_id, "name": name, "initials": _initials(name)}


def _deal_to_dict(d: Deal, db: Session = None, users_by_id: Optional[dict] = None) -> dict:
    claimed_by_id = getattr(d, "claimed_by_user_id", None)
    age_days = None
    if d.created_at:
        age_days = max(0, (datetime.utcnow() - d.created_at).days)
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
        "owner": _user_ref(db, d.owner_id, users_by_id),
        "claimed_by_user_id": claimed_by_id,
        "claimed_by": _user_ref(db, claimed_by_id, users_by_id),
        "claimed_at": d.claimed_at.isoformat() if getattr(d, "claimed_at", None) else None,
        # Truly "in the open pool" — nobody has claimed it AND nobody is assigned it.
        # An assigned-but-unclaimed deal is NOT unclaimed (it shows the owner's initials).
        "is_unclaimed": claimed_by_id is None and d.owner_id is None,
        "age_days": age_days,
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
            result["client_name"] = client.client_name

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

def _users_by_id_for_deals(db: Session, deals: list) -> dict:
    """Batch-load the users referenced (claimed_by/owner) by a page of deals."""
    ids = set()
    for d in deals:
        if d.owner_id:
            ids.add(d.owner_id)
        if getattr(d, "claimed_by_user_id", None):
            ids.add(d.claimed_by_user_id)
    if not ids:
        return {}
    rows = db.query(User).filter(User.user_id.in_(ids)).all()
    return {u.user_id: u for u in rows}


@router.get("")
def list_deals(
    stage_id: Optional[int] = None,
    value_op: Optional[str] = Query(None, description="Numeric op for value: eq/ne/lt/lte/gt/gte/between"),
    value_val: Optional[float] = None,
    value_val2: Optional[float] = None,
    probability_op: Optional[str] = Query(None, description="Numeric op for probability"),
    probability_val: Optional[float] = None,
    probability_val2: Optional[float] = None,
    created_from: Optional[str] = Query(None, description="ISO date/datetime lower bound"),
    created_to: Optional[str] = Query(None, description="ISO date/datetime upper bound"),
    claimed_by: Optional[str] = Query(None, description="user_id | 'unclaimed' | 'me'"),
    search: Optional[str] = None,
    mine: bool = False,
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

    # Numeric conditional filters (reuse the shared operator helper)
    if value_op in SIZE_OPERATORS and value_val is not None:
        clause = size_operator_clause(Deal.value, value_op, value_val, value_val2)
        if clause is not None:
            query = query.filter(clause)
    if probability_op in SIZE_OPERATORS and probability_val is not None:
        clause = size_operator_clause(Deal.probability, probability_op, probability_val, probability_val2)
        if clause is not None:
            query = query.filter(clause)

    # Date-created range
    for bound, is_lower in ((created_from, True), (created_to, False)):
        if bound:
            try:
                dt = datetime.fromisoformat(bound.replace("Z", "+00:00")).replace(tzinfo=None)
            except ValueError:
                dt = None
            if dt is not None:
                query = query.filter(Deal.created_at >= dt if is_lower else Deal.created_at <= dt)

    # Claimed-by filter
    if mine:
        query = query.filter(
            (Deal.claimed_by_user_id == user.user_id) | (Deal.owner_id == user.user_id)
        )
    elif claimed_by:
        if claimed_by == "unclaimed":
            # Open pool = neither claimed nor assigned.
            query = query.filter(Deal.claimed_by_user_id.is_(None), Deal.owner_id.is_(None))
        elif claimed_by == "me":
            query = query.filter(Deal.claimed_by_user_id == user.user_id)
        else:
            try:
                query = query.filter(Deal.claimed_by_user_id == int(claimed_by))
            except (ValueError, TypeError):
                pass

    if search:
        query = query.filter(Deal.name.ilike(f"%{search}%"))

    total = query.count()
    deals = query.order_by(Deal.created_at.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size).all()
    users_by_id = _users_by_id_for_deals(db, deals)
    return {
        "items": [_deal_to_dict(d, db, users_by_id) for d in deals],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/assignees")
def list_assignees(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Reps a deal can be assigned to, scoped to the caller.

    - Admin/super-admin: all BDMs + Recruiters in the tenant.
    - Recruiter: BDMs only (the workflow hand-off target).
    - BDM/others: none (they receive assignments, they don't assign).
    """
    base = effective_base_role(user, None, db)
    if base not in ("admin", "super_admin", "recruiter"):
        return []
    target_role = "bdm" if base == "recruiter" else None  # recruiter → BDM only
    q = db.query(User).filter(User.is_active == True)  # noqa: E712
    if tenant_id is not None:
        q = q.filter(User.tenant_id == tenant_id)
    out = []
    for u in q.all():
        b = effective_base_role(u, None, db)
        if b in ("bdm", "recruiter") and (target_role is None or b == target_role):
            out.append({"user_id": u.user_id, "label": u.full_name or u.email, "base_role": b})
    out.sort(key=lambda x: x["label"].lower())
    return out


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
            "deals": [_deal_to_dict(d, db, _users_by_id_for_deals(db, deals)) for d in deals],
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
    user: User = Depends(require_role([UserRole.ADMIN, UserRole.BDM])),
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


@router.get("/{deal_id:int}")
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

    # Job details — via the deal's contact → lead (a lead = a job posting).
    result["job"] = None
    lead = None
    if deal.contact_id:
        contact = db.query(ContactDetails).filter(ContactDetails.contact_id == deal.contact_id).first()
        if contact and contact.lead_id:
            lead = db.query(LeadDetails).filter(LeadDetails.lead_id == contact.lead_id).first()
    if lead:
        result["job"] = {
            "lead_id": lead.lead_id,
            "job_title": lead.job_title,
            "job_link": lead.job_link,
            "company": lead.client_name,
            "company_size": lead.company_size,
            "salary_min": float(lead.salary_min) if lead.salary_min else None,
            "salary_max": float(lead.salary_max) if lead.salary_max else None,
            "posting_date": str(lead.posting_date) if lead.posting_date else None,
            "location": getattr(lead, "state", None) or getattr(lead, "city", None),
        }
        # Resource Pool ATS deep link for this job.
        try:
            from app.services.integrations.resource_pool_client import build_external_ref
            from app.core.settings_resolver import get_tenant_setting
            ext = build_external_ref(lead.lead_id, deal.tenant_id)
            base = get_tenant_setting(db, "resourcepool_base_url", tenant_id=deal.tenant_id, default=None)
            result["resource_pool"] = {
                "external_ref": ext,
                "ats_url": (f"{base.rstrip('/')}/jobs/by-code/{ext}" if base else None),
            }
        except Exception:
            result["resource_pool"] = None

    result["candidate_count"] = db.query(func.count(DealCandidate.candidate_id)).filter(
        DealCandidate.deal_id == deal_id, DealCandidate.is_archived == False
    ).scalar() or 0
    return result


@router.put("/{deal_id:int}")
def update_deal(
    deal_id: int,
    data: DealUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([UserRole.ADMIN, UserRole.BDM])),
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


@router.delete("/{deal_id:int}")
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


# ─── Claim queue ──────────────────────────────────────────────────

class AssignRequest(BaseModel):
    user_id: Optional[int] = None  # None to unassign


def _get_deal_scoped(db: Session, deal_id: int, tenant_id: Optional[int]) -> Deal:
    deal = db.query(Deal).filter(Deal.deal_id == deal_id, Deal.is_archived == False).first()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    if tenant_id is not None and deal.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Deal not found")
    return deal


@router.post("/{deal_id:int}/claim")
def claim_deal(
    deal_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """A BDM/Recruiter claims an unclaimed deal (self-pull from the queue)."""
    # Authorize before loading the deal (no existence oracle for unauthorized roles).
    if effective_base_role(user, None, db) not in ("bdm", "recruiter"):
        raise HTTPException(status_code=403, detail="Only BDMs and Recruiters can claim deals")
    deal = _get_deal_scoped(db, deal_id, tenant_id)
    if deal.claimed_by_user_id is not None:
        if deal.claimed_by_user_id == user.user_id:
            return _deal_to_dict(deal, db)  # idempotent — already mine
        raise HTTPException(status_code=400, detail="Deal is already claimed")
    deal.claimed_by_user_id = user.user_id
    deal.claimed_at = datetime.utcnow()
    db.add(DealActivity(
        deal_id=deal.deal_id, activity_type="claimed",
        description=f"Claimed by {user.full_name or user.email}", created_by=user.user_id,
    ))
    db.commit()
    db.refresh(deal)
    return _deal_to_dict(deal, db)


@router.post("/{deal_id:int}/unclaim")
def unclaim_deal(
    deal_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Release a claim. Allowed for the claimer or an admin/super_admin."""
    deal = _get_deal_scoped(db, deal_id, tenant_id)
    is_admin = effective_base_role(user, None, db) in ("admin", "super_admin")
    if deal.claimed_by_user_id != user.user_id and not is_admin:
        raise HTTPException(status_code=403, detail="Only the claimer or an admin can release this deal")
    if deal.claimed_by_user_id is None:
        return _deal_to_dict(deal, db)
    deal.claimed_by_user_id = None
    deal.claimed_at = None
    db.add(DealActivity(
        deal_id=deal.deal_id, activity_type="unclaimed",
        description=f"Released by {user.full_name or user.email}", created_by=user.user_id,
    ))
    db.commit()
    db.refresh(deal)
    return _deal_to_dict(deal, db)


@router.post("/{deal_id:int}/assign")
def assign_deal(
    deal_id: int,
    body: AssignRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Assign/reassign a deal's owner.

    - Admin/super-admin: assign to any BDM/Recruiter, or unassign (None).
    - Recruiter: hand the deal off to a BDM (workflow: recruiter → BDM). Cannot unassign.
    - BDM/others: not allowed (they receive assignments).
    """
    # Authorize before loading the deal (no existence oracle for unauthorized roles).
    base = effective_base_role(user, None, db)
    is_admin = base in ("admin", "super_admin")
    is_recruiter = base == "recruiter"
    if not (is_admin or is_recruiter):
        raise HTTPException(status_code=403, detail="Only admins or recruiters can assign deals")
    deal = _get_deal_scoped(db, deal_id, tenant_id)

    target = None
    if body.user_id is not None:
        target = db.query(User).filter(User.user_id == body.user_id).first()
        if not target:
            raise HTTPException(status_code=400, detail="User not found")
        if tenant_id is not None and target.tenant_id != tenant_id:
            raise HTTPException(status_code=400, detail="User is not in this tenant")
        target_base = effective_base_role(target, None, db)
        if is_recruiter and target_base != "bdm":
            raise HTTPException(status_code=400, detail="Recruiters can only assign a deal to a BDM")
        if target_base not in ("bdm", "recruiter"):
            raise HTTPException(status_code=400, detail="Deals can only be assigned to a BDM or Recruiter")
        desc = f"Assigned to {target.full_name or target.email} by {user.full_name or user.email}"
    else:
        if not is_admin:
            raise HTTPException(status_code=400, detail="Select a BDM to assign this deal to")
        desc = f"Owner cleared by {user.full_name or user.email}"
    deal.owner_id = body.user_id
    db.add(DealActivity(
        deal_id=deal.deal_id, activity_type="assigned", description=desc, created_by=user.user_id,
    ))
    db.commit()
    db.refresh(deal)

    # Notify the assignee (in-app + email), respecting their notification prefs.
    # Skip self-assignment — no point pinging yourself.
    if target is not None and target.user_id != user.user_id:
        from app.services.deal_notifications import notify_deal_assigned
        notify_deal_assigned(db, deal, target, user, tenant_id)
        db.commit()

    return _deal_to_dict(deal, db)


# ─── Candidates submitted against a deal ──────────────────────────

def _require_rep_or_admin(db: Session, user: User):
    if effective_base_role(user, None, db) not in ("bdm", "recruiter", "admin", "super_admin"):
        raise HTTPException(status_code=403, detail="Not allowed")


@router.get("/{deal_id:int}/candidates")
def list_candidates(
    deal_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    _get_deal_scoped(db, deal_id, tenant_id)
    rows = db.query(DealCandidate).filter(
        DealCandidate.deal_id == deal_id, DealCandidate.is_archived == False
    ).order_by(DealCandidate.created_at.desc()).all()
    ids = {c.submitted_by_user_id for c in rows if c.submitted_by_user_id}
    users_by_id = {u.user_id: u for u in db.query(User).filter(User.user_id.in_(ids)).all()} if ids else {}
    return [_candidate_to_dict(c, users_by_id) for c in rows]


@router.post("/{deal_id:int}/candidates", status_code=201)
def add_candidate(
    deal_id: int,
    body: CandidateCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Submit a candidate against a deal (recruiter/BDM/admin)."""
    deal = _get_deal_scoped(db, deal_id, tenant_id)
    _require_rep_or_admin(db, user)
    status = body.status if body.status in CANDIDATE_STATUSES else "submitted"
    c = DealCandidate(
        tenant_id=deal.tenant_id, deal_id=deal_id, name=body.name, email=body.email,
        phone=body.phone, linkedin_url=body.linkedin_url, resume_url=body.resume_url,
        status=status, notes=body.notes, submitted_by_user_id=user.user_id,
    )
    db.add(c)
    db.add(DealActivity(
        deal_id=deal_id, activity_type="candidate_submitted",
        description=f"Candidate '{body.name}' submitted by {user.full_name or user.email}",
        created_by=user.user_id,
    ))
    db.commit()
    db.refresh(c)
    return _candidate_to_dict(c, {user.user_id: user})


@router.put("/{deal_id:int}/candidates/{candidate_id:int}")
def update_candidate(
    deal_id: int,
    candidate_id: int,
    body: CandidateUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    _get_deal_scoped(db, deal_id, tenant_id)
    _require_rep_or_admin(db, user)
    c = db.query(DealCandidate).filter(
        DealCandidate.candidate_id == candidate_id, DealCandidate.deal_id == deal_id,
        DealCandidate.is_archived == False,
    ).first()
    if not c:
        raise HTTPException(status_code=404, detail="Candidate not found")
    data = body.model_dump(exclude_unset=True)
    if "status" in data and data["status"] not in CANDIDATE_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status. Allowed: {CANDIDATE_STATUSES}")
    old_status = c.status
    for k, v in data.items():
        setattr(c, k, v)
    if "status" in data and data["status"] != old_status:
        db.add(DealActivity(
            deal_id=deal_id, activity_type="candidate_status",
            description=f"Candidate '{c.name}' → {data['status']} (by {user.full_name or user.email})",
            created_by=user.user_id,
        ))
    db.commit()
    db.refresh(c)
    return _candidate_to_dict(c)


@router.delete("/{deal_id:int}/candidates/{candidate_id:int}", status_code=204)
def delete_candidate(
    deal_id: int,
    candidate_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    _get_deal_scoped(db, deal_id, tenant_id)
    _require_rep_or_admin(db, user)
    c = db.query(DealCandidate).filter(
        DealCandidate.candidate_id == candidate_id, DealCandidate.deal_id == deal_id,
    ).first()
    if not c:
        raise HTTPException(status_code=404, detail="Candidate not found")
    c.is_archived = True
    db.commit()


# ─── Deal conversation (mail chain) ───────────────────────────────

def _clip(txt: Optional[str], n: int = 4000) -> Optional[str]:
    if not txt:
        return txt
    return txt if len(txt) <= n else txt[:n] + "…"


@router.get("/{deal_id:int}/messages")
def deal_messages(
    deal_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """The email conversation for the deal's contact, from the beginning — outbound
    sends (OutreachEvent) merged with the threaded inbox messages, chronological."""
    deal = _get_deal_scoped(db, deal_id, tenant_id)
    if not deal.contact_id:
        return {"contact_id": None, "messages": []}

    msgs = []
    for ev in db.query(OutreachEvent).filter(OutreachEvent.contact_id == deal.contact_id).all():
        msgs.append({
            "source": "outreach", "direction": "sent",
            "subject": ev.subject, "body": _clip(ev.body_text or ev.body_html),
            "at": ev.sent_at.isoformat() if ev.sent_at else None,
        })
        if getattr(ev, "reply_body", None):
            msgs.append({
                "source": "outreach", "direction": "received",
                "subject": getattr(ev, "reply_subject", None), "body": _clip(ev.reply_body),
                "at": ev.sent_at.isoformat() if ev.sent_at else None,
            })
    for im in db.query(InboxMessage).filter(InboxMessage.contact_id == deal.contact_id).all():
        msgs.append({
            "source": "inbox",
            "direction": im.direction.value if hasattr(im.direction, "value") else str(im.direction),
            "subject": im.subject, "body": _clip(im.body_text or im.body_html),
            "from": im.from_email, "to": im.to_email, "category": im.category,
            "at": im.received_at.isoformat() if im.received_at else None,
        })
    msgs.sort(key=lambda m: (m["at"] or ""))
    return {"contact_id": deal.contact_id, "messages": msgs}


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

@router.post("/{deal_id:int}/activities")
def add_activity(
    deal_id: int,
    data: ActivityCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([UserRole.ADMIN, UserRole.BDM])),
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
