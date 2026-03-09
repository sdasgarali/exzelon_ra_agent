"""Campaign CRUD + management API endpoints."""
import json
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps.database import get_db
from app.api.deps.auth import get_current_active_user, require_role
from app.db.models.user import User, UserRole
from app.db.models.campaign import (
    Campaign, SequenceStep, CampaignContact,
    CampaignStatus, StepType, CampaignContactStatus,
)

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


# ─── Schemas ───────────────────────────────────────────────────────

class EnrollmentRules(BaseModel):
    enabled: bool = False
    validation_status: List[str] = ["Valid"]
    priority_levels: List[str] = []
    states: List[str] = []
    job_title_keywords: List[str] = []
    sources: List[str] = []
    min_lead_score: Optional[int] = None
    max_per_run: int = 50
    daily_cap: int = 200

class CampaignCreate(BaseModel):
    name: str = Field(..., max_length=255)
    description: Optional[str] = None
    timezone: str = "UTC"
    send_window_start: str = "09:00"
    send_window_end: str = "17:00"
    send_days: List[str] = ["mon", "tue", "wed", "thu", "fri"]
    mailbox_ids: List[int] = []
    daily_limit: int = 30
    enrollment_rules: Optional[EnrollmentRules] = None

class CampaignUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    timezone: Optional[str] = None
    send_window_start: Optional[str] = None
    send_window_end: Optional[str] = None
    send_days: Optional[List[str]] = None
    mailbox_ids: Optional[List[int]] = None
    daily_limit: Optional[int] = None
    enrollment_rules: Optional[EnrollmentRules] = None

class StepCreate(BaseModel):
    step_type: str  # email/wait/condition
    step_order: Optional[int] = None
    subject: Optional[str] = None
    body_html: Optional[str] = None
    body_text: Optional[str] = None
    template_id: Optional[int] = None
    delay_days: int = 1
    delay_hours: int = 0
    reply_to_thread: bool = True
    condition_type: Optional[str] = None
    condition_window_hours: Optional[int] = 24
    yes_next_step: Optional[int] = None
    no_next_step: Optional[int] = None
    variants_json: Optional[str] = None

class StepUpdate(BaseModel):
    subject: Optional[str] = None
    body_html: Optional[str] = None
    body_text: Optional[str] = None
    template_id: Optional[int] = None
    delay_days: Optional[int] = None
    delay_hours: Optional[int] = None
    reply_to_thread: Optional[bool] = None
    condition_type: Optional[str] = None
    condition_window_hours: Optional[int] = None
    yes_next_step: Optional[int] = None
    no_next_step: Optional[int] = None
    variants_json: Optional[str] = None

class StepReorder(BaseModel):
    step_ids: List[int]  # ordered list of step_ids

class ContactEnroll(BaseModel):
    contact_ids: List[int]

class ContactRemove(BaseModel):
    contact_ids: List[int]


# ─── Helpers ───────────────────────────────────────────────────────

def _campaign_to_dict(c: Campaign, include_steps: bool = False, db: Session = None) -> dict:
    d = {
        "campaign_id": c.campaign_id,
        "name": c.name,
        "description": c.description,
        "status": c.status.value if c.status else "draft",
        "timezone": c.timezone,
        "send_window_start": c.send_window_start,
        "send_window_end": c.send_window_end,
        "send_days": json.loads(c.send_days_json) if c.send_days_json else [],
        "mailbox_ids": json.loads(c.mailbox_ids_json) if c.mailbox_ids_json else [],
        "daily_limit": c.daily_limit,
        "total_contacts": c.total_contacts,
        "total_sent": c.total_sent,
        "total_opened": c.total_opened,
        "total_replied": c.total_replied,
        "total_bounced": c.total_bounced,
        "created_by": c.created_by,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
        "is_archived": c.is_archived,
        "enrollment_rules": json.loads(c.enrollment_rules_json) if c.enrollment_rules_json else None,
        "auto_enrolled_today": c.auto_enrolled_today or 0,
    }
    if include_steps and db:
        steps = db.query(SequenceStep).filter(
            SequenceStep.campaign_id == c.campaign_id
        ).order_by(SequenceStep.step_order).all()
        d["steps"] = [_step_to_dict(s) for s in steps]
    return d


def _step_to_dict(s: SequenceStep) -> dict:
    return {
        "step_id": s.step_id,
        "campaign_id": s.campaign_id,
        "step_order": s.step_order,
        "step_type": s.step_type.value if s.step_type else "email",
        "subject": s.subject,
        "body_html": s.body_html,
        "body_text": s.body_text,
        "template_id": s.template_id,
        "delay_days": s.delay_days,
        "delay_hours": s.delay_hours,
        "reply_to_thread": s.reply_to_thread,
        "condition_type": s.condition_type,
        "condition_window_hours": s.condition_window_hours,
        "yes_next_step": s.yes_next_step,
        "no_next_step": s.no_next_step,
        "variants_json": s.variants_json,
        "total_sent": s.total_sent,
        "total_opened": s.total_opened,
        "total_clicked": s.total_clicked,
        "total_replied": s.total_replied,
        "total_bounced": s.total_bounced,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }


def _cc_to_dict(cc: CampaignContact) -> dict:
    return {
        "id": cc.id,
        "campaign_id": cc.campaign_id,
        "contact_id": cc.contact_id,
        "lead_id": cc.lead_id,
        "status": cc.status.value if cc.status else "active",
        "current_step": cc.current_step,
        "next_send_at": cc.next_send_at.isoformat() if cc.next_send_at else None,
        "enrolled_at": cc.enrolled_at.isoformat() if cc.enrolled_at else None,
        "completed_at": cc.completed_at.isoformat() if cc.completed_at else None,
    }


# ─── Campaign CRUD ────────────────────────────────────────────────

@router.get("")
def list_campaigns(
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    query = db.query(Campaign).filter(Campaign.is_archived == False)
    if status:
        query = query.filter(Campaign.status == status)
    total = query.count()
    campaigns = query.order_by(Campaign.created_at.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size).all()
    return {
        "items": [_campaign_to_dict(c) for c in campaigns],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size,
    }


@router.post("")
def create_campaign(
    data: CampaignCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR])),
):
    campaign = Campaign(
        name=data.name,
        description=data.description,
        status=CampaignStatus.DRAFT,
        timezone=data.timezone,
        send_window_start=data.send_window_start,
        send_window_end=data.send_window_end,
        send_days_json=json.dumps(data.send_days),
        mailbox_ids_json=json.dumps(data.mailbox_ids) if data.mailbox_ids else None,
        daily_limit=data.daily_limit,
        enrollment_rules_json=json.dumps(data.enrollment_rules.model_dump()) if data.enrollment_rules else None,
        created_by=user.user_id,
    )
    db.add(campaign)
    db.commit()
    db.refresh(campaign)
    return _campaign_to_dict(campaign)


@router.get("/{campaign_id}")
def get_campaign(
    campaign_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    campaign = db.query(Campaign).filter(Campaign.campaign_id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return _campaign_to_dict(campaign, include_steps=True, db=db)


@router.put("/{campaign_id}")
def update_campaign(
    campaign_id: int,
    data: CampaignUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR])),
):
    campaign = db.query(Campaign).filter(Campaign.campaign_id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    if data.name is not None:
        campaign.name = data.name
    if data.description is not None:
        campaign.description = data.description
    if data.timezone is not None:
        campaign.timezone = data.timezone
    if data.send_window_start is not None:
        campaign.send_window_start = data.send_window_start
    if data.send_window_end is not None:
        campaign.send_window_end = data.send_window_end
    if data.send_days is not None:
        campaign.send_days_json = json.dumps(data.send_days)
    if data.mailbox_ids is not None:
        campaign.mailbox_ids_json = json.dumps(data.mailbox_ids)
    if data.daily_limit is not None:
        campaign.daily_limit = data.daily_limit
    if data.enrollment_rules is not None:
        campaign.enrollment_rules_json = json.dumps(data.enrollment_rules.model_dump())

    db.commit()
    db.refresh(campaign)
    return _campaign_to_dict(campaign, include_steps=True, db=db)


@router.delete("/{campaign_id}")
def archive_campaign(
    campaign_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([UserRole.ADMIN])),
):
    campaign = db.query(Campaign).filter(Campaign.campaign_id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    campaign.status = CampaignStatus.ARCHIVED
    campaign.is_archived = True
    db.commit()
    return {"message": "Campaign archived"}


# ─── Campaign Status Actions ──────────────────────────────────────

@router.post("/{campaign_id}/activate")
def activate_campaign(
    campaign_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR])),
):
    campaign = db.query(Campaign).filter(Campaign.campaign_id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    # Validate: must have at least one email step
    email_steps = db.query(SequenceStep).filter(
        SequenceStep.campaign_id == campaign_id,
        SequenceStep.step_type == StepType.EMAIL,
    ).count()
    if email_steps == 0:
        raise HTTPException(status_code=400, detail="Campaign must have at least one email step")

    campaign.status = CampaignStatus.ACTIVE

    # Set next_send_at for enrolled contacts that don't have one
    pending = db.query(CampaignContact).filter(
        CampaignContact.campaign_id == campaign_id,
        CampaignContact.status == CampaignContactStatus.ACTIVE,
        CampaignContact.next_send_at.is_(None),
    ).all()
    now = datetime.utcnow()
    for cc in pending:
        step = db.query(SequenceStep).filter(
            SequenceStep.campaign_id == campaign_id,
            SequenceStep.step_order == cc.current_step,
        ).first()
        if step:
            from datetime import timedelta
            cc.next_send_at = now + timedelta(days=step.delay_days, hours=step.delay_hours)

    db.commit()

    # Dispatch webhook event
    try:
        from app.services.webhook_dispatcher import dispatch_webhook_event
        dispatch_webhook_event("campaign.started", {
            "campaign_id": campaign.campaign_id,
            "name": campaign.name,
        }, db)
    except Exception:
        pass

    return {"message": "Campaign activated", "status": "active"}


@router.post("/{campaign_id}/pause")
def pause_campaign(
    campaign_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR])),
):
    campaign = db.query(Campaign).filter(Campaign.campaign_id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    campaign.status = CampaignStatus.PAUSED
    db.commit()

    try:
        from app.services.webhook_dispatcher import dispatch_webhook_event
        dispatch_webhook_event("campaign.paused", {
            "campaign_id": campaign.campaign_id,
            "name": campaign.name,
        }, db)
    except Exception:
        pass

    return {"message": "Campaign paused", "status": "paused"}


@router.post("/{campaign_id}/resume")
def resume_campaign(
    campaign_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR])),
):
    campaign = db.query(Campaign).filter(Campaign.campaign_id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    campaign.status = CampaignStatus.ACTIVE
    db.commit()
    return {"message": "Campaign resumed", "status": "active"}


# ─── Sequence Steps ───────────────────────────────────────────────

@router.get("/{campaign_id}/steps")
def list_steps(
    campaign_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    steps = db.query(SequenceStep).filter(
        SequenceStep.campaign_id == campaign_id
    ).order_by(SequenceStep.step_order).all()
    return [_step_to_dict(s) for s in steps]


@router.post("/{campaign_id}/steps")
def add_step(
    campaign_id: int,
    data: StepCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR])),
):
    campaign = db.query(Campaign).filter(Campaign.campaign_id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    # Determine step order
    if data.step_order is not None:
        order = data.step_order
    else:
        max_order = db.query(SequenceStep).filter(
            SequenceStep.campaign_id == campaign_id
        ).count()
        order = max_order + 1

    step = SequenceStep(
        campaign_id=campaign_id,
        step_order=order,
        step_type=StepType(data.step_type),
        subject=data.subject,
        body_html=data.body_html,
        body_text=data.body_text,
        template_id=data.template_id,
        delay_days=data.delay_days,
        delay_hours=data.delay_hours,
        reply_to_thread=data.reply_to_thread,
        condition_type=data.condition_type,
        condition_window_hours=data.condition_window_hours,
        yes_next_step=data.yes_next_step,
        no_next_step=data.no_next_step,
        variants_json=data.variants_json,
    )
    db.add(step)
    db.commit()
    db.refresh(step)
    return _step_to_dict(step)


@router.put("/{campaign_id}/steps/{step_id}")
def update_step(
    campaign_id: int,
    step_id: int,
    data: StepUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR])),
):
    step = db.query(SequenceStep).filter(
        SequenceStep.step_id == step_id,
        SequenceStep.campaign_id == campaign_id,
    ).first()
    if not step:
        raise HTTPException(status_code=404, detail="Step not found")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(step, field, value)

    db.commit()
    db.refresh(step)
    return _step_to_dict(step)


@router.delete("/{campaign_id}/steps/{step_id}")
def delete_step(
    campaign_id: int,
    step_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR])),
):
    step = db.query(SequenceStep).filter(
        SequenceStep.step_id == step_id,
        SequenceStep.campaign_id == campaign_id,
    ).first()
    if not step:
        raise HTTPException(status_code=404, detail="Step not found")

    deleted_order = step.step_order
    db.delete(step)

    # Reorder remaining steps
    remaining = db.query(SequenceStep).filter(
        SequenceStep.campaign_id == campaign_id,
        SequenceStep.step_order > deleted_order,
    ).order_by(SequenceStep.step_order).all()
    for s in remaining:
        s.step_order -= 1

    db.commit()
    return {"message": "Step deleted"}


@router.put("/{campaign_id}/steps/reorder")
def reorder_steps(
    campaign_id: int,
    data: StepReorder,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR])),
):
    for new_order, step_id in enumerate(data.step_ids, start=1):
        step = db.query(SequenceStep).filter(
            SequenceStep.step_id == step_id,
            SequenceStep.campaign_id == campaign_id,
        ).first()
        if step:
            step.step_order = new_order
    db.commit()
    return {"message": "Steps reordered"}


# ─── Campaign Contacts ────────────────────────────────────────────

@router.post("/{campaign_id}/contacts")
def enroll_contacts(
    campaign_id: int,
    data: ContactEnroll,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR])),
):
    from app.services.campaign_engine import enroll_contacts as _enroll
    result = _enroll(campaign_id, data.contact_ids, db)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.delete("/{campaign_id}/contacts")
def remove_contacts(
    campaign_id: int,
    data: ContactRemove,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR])),
):
    deleted = db.query(CampaignContact).filter(
        CampaignContact.campaign_id == campaign_id,
        CampaignContact.contact_id.in_(data.contact_ids),
    ).delete(synchronize_session=False)
    db.commit()
    return {"removed": deleted}


@router.get("/{campaign_id}/contacts")
def list_campaign_contacts(
    campaign_id: int,
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    query = db.query(CampaignContact).filter(
        CampaignContact.campaign_id == campaign_id
    )
    if status:
        query = query.filter(CampaignContact.status == status)
    total = query.count()
    items = query.order_by(CampaignContact.enrolled_at.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size).all()

    # Enrich with contact details
    contact_ids = [cc.contact_id for cc in items]
    from app.db.models.contact import ContactDetails
    contacts_map = {}
    if contact_ids:
        contacts = db.query(ContactDetails).filter(
            ContactDetails.contact_id.in_(contact_ids)
        ).all()
        contacts_map = {c.contact_id: c for c in contacts}

    enriched = []
    for cc in items:
        d = _cc_to_dict(cc)
        c = contacts_map.get(cc.contact_id)
        if c:
            d["contact_name"] = f"{c.first_name or ''} {c.last_name or ''}".strip()
            d["contact_email"] = c.email
            d["contact_company"] = c.client_name
        enriched.append(d)

    return {
        "items": enriched,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size,
    }


class EnrollmentPreviewRequest(BaseModel):
    rules: EnrollmentRules


@router.post("/{campaign_id}/enrollment-preview")
def enrollment_preview(
    campaign_id: int,
    data: EnrollmentPreviewRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """Preview how many contacts match the given enrollment rules."""
    campaign = db.query(Campaign).filter(Campaign.campaign_id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    from app.services.auto_enrollment import preview_enrollment_matches
    count = preview_enrollment_matches(campaign_id, data.rules.model_dump(), db)
    return {"count": count}


@router.post("/{campaign_id}/auto-enroll")
def trigger_auto_enroll(
    campaign_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR])),
):
    """Manually trigger auto-enrollment for one campaign."""
    campaign = db.query(Campaign).filter(Campaign.campaign_id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if campaign.status != CampaignStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="Campaign must be active for auto-enrollment")
    from app.services.auto_enrollment import run_auto_enrollment_for_campaign
    result = run_auto_enrollment_for_campaign(campaign, db)
    return result


# ─── Analytics ─────────────────────────────────────────────────────

@router.get("/{campaign_id}/analytics")
def campaign_analytics(
    campaign_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    campaign = db.query(Campaign).filter(Campaign.campaign_id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    from app.db.models.outreach import OutreachEvent, OutreachStatus

    # Overall stats
    total_contacts = db.query(CampaignContact).filter(
        CampaignContact.campaign_id == campaign_id
    ).count()
    active = db.query(CampaignContact).filter(
        CampaignContact.campaign_id == campaign_id,
        CampaignContact.status == CampaignContactStatus.ACTIVE,
    ).count()
    completed = db.query(CampaignContact).filter(
        CampaignContact.campaign_id == campaign_id,
        CampaignContact.status == CampaignContactStatus.COMPLETED,
    ).count()
    replied = db.query(CampaignContact).filter(
        CampaignContact.campaign_id == campaign_id,
        CampaignContact.status == CampaignContactStatus.REPLIED,
    ).count()
    bounced = db.query(CampaignContact).filter(
        CampaignContact.campaign_id == campaign_id,
        CampaignContact.status == CampaignContactStatus.BOUNCED,
    ).count()

    # Per-step stats
    steps = db.query(SequenceStep).filter(
        SequenceStep.campaign_id == campaign_id
    ).order_by(SequenceStep.step_order).all()

    step_analytics = []
    for step in steps:
        sent = db.query(OutreachEvent).filter(
            OutreachEvent.step_id == step.step_id,
            OutreachEvent.status == OutreachStatus.SENT,
        ).count()

        step_replied = db.query(OutreachEvent).filter(
            OutreachEvent.step_id == step.step_id,
            OutreachEvent.reply_detected_at.isnot(None),
        ).count()

        step_analytics.append({
            "step_id": step.step_id,
            "step_order": step.step_order,
            "step_type": step.step_type.value if step.step_type else "email",
            "subject": step.subject,
            "sent": sent,
            "replied": step_replied,
            "reply_rate": round(step_replied / sent * 100, 1) if sent > 0 else 0,
        })

    # Funnel: contacts at each step
    funnel = []
    for step in steps:
        at_step = db.query(CampaignContact).filter(
            CampaignContact.campaign_id == campaign_id,
            CampaignContact.current_step == step.step_order,
            CampaignContact.status == CampaignContactStatus.ACTIVE,
        ).count()
        funnel.append({
            "step_order": step.step_order,
            "step_type": step.step_type.value if step.step_type else "email",
            "contacts_at_step": at_step,
        })

    return {
        "overall": {
            "total_contacts": total_contacts,
            "active": active,
            "completed": completed,
            "replied": replied,
            "bounced": bounced,
        },
        "steps": step_analytics,
        "funnel": funnel,
    }


# ─── Duplicate ─────────────────────────────────────────────────────

@router.post("/{campaign_id}/duplicate")
def duplicate_campaign(
    campaign_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR])),
):
    original = db.query(Campaign).filter(Campaign.campaign_id == campaign_id).first()
    if not original:
        raise HTTPException(status_code=404, detail="Campaign not found")

    clone = Campaign(
        name=f"{original.name} (Copy)",
        description=original.description,
        status=CampaignStatus.DRAFT,
        timezone=original.timezone,
        send_window_start=original.send_window_start,
        send_window_end=original.send_window_end,
        send_days_json=original.send_days_json,
        mailbox_ids_json=original.mailbox_ids_json,
        daily_limit=original.daily_limit,
        enrollment_rules_json=original.enrollment_rules_json,
        created_by=user.user_id,
    )
    db.add(clone)
    db.flush()

    # Clone steps
    steps = db.query(SequenceStep).filter(
        SequenceStep.campaign_id == campaign_id
    ).order_by(SequenceStep.step_order).all()
    for s in steps:
        new_step = SequenceStep(
            campaign_id=clone.campaign_id,
            step_order=s.step_order,
            step_type=s.step_type,
            subject=s.subject,
            body_html=s.body_html,
            body_text=s.body_text,
            template_id=s.template_id,
            delay_days=s.delay_days,
            delay_hours=s.delay_hours,
            reply_to_thread=s.reply_to_thread,
            condition_type=s.condition_type,
            condition_window_hours=s.condition_window_hours,
            yes_next_step=s.yes_next_step,
            no_next_step=s.no_next_step,
            variants_json=s.variants_json,
        )
        db.add(new_step)

    db.commit()
    db.refresh(clone)
    return _campaign_to_dict(clone, include_steps=True, db=db)
