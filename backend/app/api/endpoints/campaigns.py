"""Campaign CRUD + management API endpoints."""
import json
import structlog
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

logger = structlog.get_logger()

from app.api.deps.database import get_db
from app.api.deps.auth import get_current_active_user, require_role, get_current_tenant_id
from app.core.rate_limiter import limiter
from app.api.deps.plan_limits import check_plan_limit
from app.db.query_helpers import tenant_filter
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
    preview_mode: bool = False
    scheduled_send_at: Optional[str] = None  # ISO datetime for future send
    sending_speed: str = "normal"  # relaxed/normal/aggressive

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
    preview_mode: Optional[bool] = None
    scheduled_send_at: Optional[str] = None  # ISO datetime for future send
    sending_speed: Optional[str] = None  # relaxed/normal/aggressive

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
        "preview_mode": getattr(c, 'preview_mode', False) or False,
        "scheduled_send_at": c.scheduled_send_at.isoformat() if getattr(c, 'scheduled_send_at', None) else None,
        "sending_speed": getattr(c, 'sending_speed', 'normal') or 'normal',
        "health_score": getattr(c, 'health_score', None),
        "slow_ramp_enabled": getattr(c, 'slow_ramp_enabled', False) or False,
        "slow_ramp_increment": getattr(c, 'slow_ramp_increment', 2) or 2,
        "slow_ramp_current_day": getattr(c, 'slow_ramp_current_day', 0) or 0,
        "bounce_threshold": getattr(c, 'bounce_threshold', 10),
        "spam_threshold": getattr(c, 'spam_threshold', 5),
        "auto_pause_reason": getattr(c, 'auto_pause_reason', None),
        "auto_reply_enabled": getattr(c, 'auto_reply_enabled', False) or False,
        "assignment_mode": getattr(c, 'assignment_mode', 'manual') or 'manual',
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
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    query = db.query(Campaign).filter(Campaign.is_archived == False)
    query = tenant_filter(query, Campaign, tenant_id)
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
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    check_plan_limit(db, tenant_id, "campaigns")

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
        tenant_id=tenant_id or 1,
        preview_mode=data.preview_mode,
        sending_speed=data.sending_speed if data.sending_speed in ('relaxed', 'normal', 'aggressive') else 'normal',
    )
    if data.scheduled_send_at:
        from datetime import datetime as dt
        try:
            campaign.scheduled_send_at = dt.fromisoformat(data.scheduled_send_at.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            pass
    db.add(campaign)
    db.commit()
    db.refresh(campaign)
    return _campaign_to_dict(campaign)


@router.get("/{campaign_id}")
def get_campaign(
    campaign_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    campaign = db.query(Campaign).filter(Campaign.campaign_id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if tenant_id is not None and campaign.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return _campaign_to_dict(campaign, include_steps=True, db=db)


@router.put("/{campaign_id}")
def update_campaign(
    campaign_id: int,
    data: CampaignUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    campaign = db.query(Campaign).filter(Campaign.campaign_id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if tenant_id is not None and campaign.tenant_id != tenant_id:
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
    if data.preview_mode is not None:
        campaign.preview_mode = data.preview_mode
    if data.sending_speed is not None and data.sending_speed in ('relaxed', 'normal', 'aggressive'):
        campaign.sending_speed = data.sending_speed
    if data.scheduled_send_at is not None:
        from datetime import datetime as dt
        try:
            campaign.scheduled_send_at = dt.fromisoformat(data.scheduled_send_at.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            campaign.scheduled_send_at = None

    db.commit()
    db.refresh(campaign)
    return _campaign_to_dict(campaign, include_steps=True, db=db)


@router.delete("/{campaign_id}")
def archive_campaign(
    campaign_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([UserRole.ADMIN])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    campaign = db.query(Campaign).filter(Campaign.campaign_id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if tenant_id is not None and campaign.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Campaign not found")
    from app.core.state_machine import validate_campaign_transition
    if not validate_campaign_transition(campaign.status, CampaignStatus.ARCHIVED):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot archive campaign in '{campaign.status.value}' status",
        )
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
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    from app.core.settings_resolver import get_tenant_setting_bool
    if not get_tenant_setting_bool(db, "feature_campaigns_enabled", tenant_id=tenant_id, default=True):
        raise HTTPException(status_code=403, detail="Campaign execution is disabled for your organization")

    campaign = db.query(Campaign).filter(Campaign.campaign_id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if tenant_id is not None and campaign.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Campaign not found")

    from app.core.state_machine import validate_campaign_transition
    if not validate_campaign_transition(campaign.status, CampaignStatus.ACTIVE):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot activate campaign in '{campaign.status.value}' status",
        )

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
    except Exception as e_wh:
        logger.warning("Webhook dispatch failed for campaign.started",
                       campaign_id=campaign.campaign_id, error=str(e_wh))

    return {"message": "Campaign activated", "status": "active"}


@router.post("/{campaign_id}/pause")
def pause_campaign(
    campaign_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    campaign = db.query(Campaign).filter(Campaign.campaign_id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if tenant_id is not None and campaign.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Campaign not found")
    from app.core.state_machine import validate_campaign_transition
    if not validate_campaign_transition(campaign.status, CampaignStatus.PAUSED):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot pause campaign in '{campaign.status.value}' status",
        )
    campaign.status = CampaignStatus.PAUSED
    db.commit()

    try:
        from app.services.webhook_dispatcher import dispatch_webhook_event
        dispatch_webhook_event("campaign.paused", {
            "campaign_id": campaign.campaign_id,
            "name": campaign.name,
        }, db)
    except Exception as e_wh:
        logger.warning("Webhook dispatch failed for campaign.paused",
                       campaign_id=campaign.campaign_id, error=str(e_wh))

    return {"message": "Campaign paused", "status": "paused"}


@router.post("/{campaign_id}/resume")
def resume_campaign(
    campaign_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    campaign = db.query(Campaign).filter(Campaign.campaign_id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if tenant_id is not None and campaign.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Campaign not found")
    from app.core.state_machine import validate_campaign_transition
    if not validate_campaign_transition(campaign.status, CampaignStatus.ACTIVE):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot resume campaign in '{campaign.status.value}' status",
        )
    campaign.status = CampaignStatus.ACTIVE
    db.commit()
    return {"message": "Campaign resumed", "status": "active"}


# ─── Sequence Steps ───────────────────────────────────────────────

@router.get("/{campaign_id}/steps")
def list_steps(
    campaign_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    campaign = db.query(Campaign).filter(Campaign.campaign_id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if tenant_id is not None and campaign.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Campaign not found")

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
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    campaign = db.query(Campaign).filter(Campaign.campaign_id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if tenant_id is not None and campaign.tenant_id != tenant_id:
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
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    campaign = db.query(Campaign).filter(Campaign.campaign_id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if tenant_id is not None and campaign.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Campaign not found")

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
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    campaign = db.query(Campaign).filter(Campaign.campaign_id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if tenant_id is not None and campaign.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Campaign not found")

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
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    campaign = db.query(Campaign).filter(Campaign.campaign_id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if tenant_id is not None and campaign.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Campaign not found")

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
@limiter.limit("20/hour")
def enroll_contacts(
    request: Request,
    campaign_id: int,
    data: ContactEnroll,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    campaign = db.query(Campaign).filter(Campaign.campaign_id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if tenant_id is not None and campaign.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Campaign not found")

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
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    campaign = db.query(Campaign).filter(Campaign.campaign_id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if tenant_id is not None and campaign.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Campaign not found")

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
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    campaign = db.query(Campaign).filter(Campaign.campaign_id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if tenant_id is not None and campaign.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Campaign not found")

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
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Preview how many contacts match the given enrollment rules."""
    campaign = db.query(Campaign).filter(Campaign.campaign_id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if tenant_id is not None and campaign.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Campaign not found")

    from app.services.auto_enrollment import preview_enrollment_matches
    count = preview_enrollment_matches(campaign_id, data.rules.model_dump(), db)
    return {"count": count}


@router.post("/{campaign_id}/auto-enroll")
def trigger_auto_enroll(
    campaign_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Manually trigger auto-enrollment for one campaign."""
    campaign = db.query(Campaign).filter(Campaign.campaign_id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if tenant_id is not None and campaign.tenant_id != tenant_id:
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
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Campaign analytics with optional date range filter (YYYY-MM-DD)."""
    campaign = db.query(Campaign).filter(Campaign.campaign_id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if tenant_id is not None and campaign.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Campaign not found")

    from app.db.models.outreach import OutreachEvent, OutreachStatus
    from datetime import datetime as dt

    # Parse date range
    start_dt = None
    end_dt = None
    if date_from:
        try:
            start_dt = dt.strptime(date_from, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=400, detail="date_from must be YYYY-MM-DD")
    if date_to:
        try:
            end_dt = dt.strptime(date_to, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
        except ValueError:
            raise HTTPException(status_code=400, detail="date_to must be YYYY-MM-DD")

    # Overall stats — contact-level (not date-filtered, contacts are cumulative)
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

    # Build base event query with optional date filter
    def _event_query():
        q = db.query(OutreachEvent).filter(OutreachEvent.campaign_id == campaign_id)
        if start_dt:
            q = q.filter(OutreachEvent.sent_at >= start_dt)
        if end_dt:
            q = q.filter(OutreachEvent.sent_at <= end_dt)
        return q

    # Calculate overall opened/clicked
    total_sent_events = _event_query().filter(
        OutreachEvent.status == OutreachStatus.SENT,
    ).count()
    total_opened_events = _event_query().filter(
        OutreachEvent.opened_at.isnot(None),
    ).count()
    total_clicked_events = _event_query().filter(
        OutreachEvent.clicked_at.isnot(None),
    ).count()

    step_analytics = []
    for step in steps:
        def _step_query(step_id=step.step_id):
            q = db.query(OutreachEvent).filter(OutreachEvent.step_id == step_id)
            if start_dt:
                q = q.filter(OutreachEvent.sent_at >= start_dt)
            if end_dt:
                q = q.filter(OutreachEvent.sent_at <= end_dt)
            return q

        sent = _step_query().filter(OutreachEvent.status == OutreachStatus.SENT).count()
        step_opened = _step_query().filter(OutreachEvent.opened_at.isnot(None)).count()
        step_clicked = _step_query().filter(OutreachEvent.clicked_at.isnot(None)).count()
        step_replied = _step_query().filter(OutreachEvent.reply_detected_at.isnot(None)).count()
        step_bounced = _step_query().filter(OutreachEvent.status == OutreachStatus.BOUNCED).count()

        # Per-variant breakdown
        variant_stats = []
        if step.variants_json:
            try:
                variants = json.loads(step.variants_json)
                for vi, variant in enumerate(variants):
                    v_sent = _step_query().filter(OutreachEvent.status == OutreachStatus.SENT, OutreachEvent.variant_index == vi).count()
                    v_opened = _step_query().filter(OutreachEvent.opened_at.isnot(None), OutreachEvent.variant_index == vi).count()
                    v_clicked = _step_query().filter(OutreachEvent.clicked_at.isnot(None), OutreachEvent.variant_index == vi).count()
                    v_replied = _step_query().filter(OutreachEvent.reply_detected_at.isnot(None), OutreachEvent.variant_index == vi).count()
                    v_bounced = _step_query().filter(OutreachEvent.status == OutreachStatus.BOUNCED, OutreachEvent.variant_index == vi).count()
                    variant_stats.append({
                        "variant_index": vi,
                        "subject": variant.get("subject", ""),
                        "sent": v_sent,
                        "opened": v_opened,
                        "open_rate": round(v_opened / v_sent * 100, 1) if v_sent > 0 else 0,
                        "clicked": v_clicked,
                        "click_rate": round(v_clicked / v_sent * 100, 1) if v_sent > 0 else 0,
                        "replied": v_replied,
                        "reply_rate": round(v_replied / v_sent * 100, 1) if v_sent > 0 else 0,
                        "bounced": v_bounced,
                        "bounce_rate": round(v_bounced / v_sent * 100, 1) if v_sent > 0 else 0,
                    })
            except (json.JSONDecodeError, TypeError):
                pass

        step_analytics.append({
            "step_id": step.step_id,
            "step_order": step.step_order,
            "step_type": step.step_type.value if step.step_type else "email",
            "subject": step.subject,
            "sent": sent,
            "opened": step_opened,
            "open_rate": round(step_opened / sent * 100, 1) if sent > 0 else 0,
            "clicked": step_clicked,
            "click_rate": round(step_clicked / sent * 100, 1) if sent > 0 else 0,
            "replied": step_replied,
            "reply_rate": round(step_replied / sent * 100, 1) if sent > 0 else 0,
            "bounced": step_bounced,
            "bounce_rate": round(step_bounced / sent * 100, 1) if sent > 0 else 0,
            "variants": variant_stats,
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
            "total_sent": total_sent_events,
            "total_opened": total_opened_events,
            "open_rate": round(total_opened_events / total_sent_events * 100, 1) if total_sent_events > 0 else 0,
            "total_clicked": total_clicked_events,
            "click_rate": round(total_clicked_events / total_sent_events * 100, 1) if total_sent_events > 0 else 0,
            "replied": replied,
            "reply_rate": round(replied / total_contacts * 100, 1) if total_contacts > 0 else 0,
            "bounced": bounced,
            "bounce_rate": round(bounced / total_contacts * 100, 1) if total_contacts > 0 else 0,
        },
        "steps": step_analytics,
        "funnel": funnel,
        "date_range": {"from": date_from, "to": date_to},
    }


# ─── Daily Trend & CSV Export ────────────────────────────────────

@router.get("/{campaign_id}/analytics/daily")
def campaign_daily_analytics(
    campaign_id: int,
    days: int = 30,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Get daily send/open/reply/bounce trend for a campaign."""
    campaign = db.query(Campaign).filter(Campaign.campaign_id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if tenant_id is not None and campaign.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Campaign not found")

    from app.db.models.outreach import OutreachEvent, OutreachStatus
    from datetime import datetime as dt, timedelta
    from sqlalchemy import func, cast, Date

    start = dt.utcnow() - timedelta(days=days)
    daily_data = []

    for i in range(days):
        day = start + timedelta(days=i)
        day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day.replace(hour=23, minute=59, second=59)

        base_q = db.query(OutreachEvent).filter(
            OutreachEvent.campaign_id == campaign_id,
            OutreachEvent.sent_at >= day_start,
            OutreachEvent.sent_at <= day_end,
        )

        sent = base_q.filter(OutreachEvent.status == OutreachStatus.SENT).count()
        opened = base_q.filter(OutreachEvent.opened_at.isnot(None)).count()
        clicked = base_q.filter(OutreachEvent.clicked_at.isnot(None)).count()
        replied = base_q.filter(OutreachEvent.reply_detected_at.isnot(None)).count()
        bounced = base_q.filter(OutreachEvent.status == OutreachStatus.BOUNCED).count()

        if sent > 0 or opened > 0 or replied > 0:
            daily_data.append({
                "date": day.strftime("%Y-%m-%d"),
                "sent": sent,
                "opened": opened,
                "clicked": clicked,
                "replied": replied,
                "bounced": bounced,
            })

    return {"campaign_id": campaign_id, "days": days, "daily": daily_data}


@router.get("/{campaign_id}/analytics/export")
def export_campaign_analytics_csv(
    campaign_id: int,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Export campaign analytics as CSV."""
    campaign = db.query(Campaign).filter(Campaign.campaign_id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if tenant_id is not None and campaign.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Campaign not found")

    from app.db.models.outreach import OutreachEvent, OutreachStatus
    from app.db.models.contact import ContactDetails
    import csv
    import io

    events_query = db.query(OutreachEvent).filter(
        OutreachEvent.campaign_id == campaign_id,
        OutreachEvent.status == OutreachStatus.SENT,
    )
    if date_from:
        from datetime import datetime as dt
        try:
            events_query = events_query.filter(OutreachEvent.sent_at >= dt.strptime(date_from, "%Y-%m-%d"))
        except ValueError:
            pass
    if date_to:
        from datetime import datetime as dt
        try:
            events_query = events_query.filter(OutreachEvent.sent_at <= dt.strptime(date_to, "%Y-%m-%d").replace(hour=23, minute=59, second=59))
        except ValueError:
            pass
    events = events_query.all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "event_id", "contact_id", "contact_email", "contact_name",
        "step_id", "variant_index", "subject", "sent_at",
        "opened_at", "clicked_at", "replied_at", "status",
    ])

    for ev in events:
        contact = db.query(ContactDetails).filter(
            ContactDetails.contact_id == ev.contact_id
        ).first()
        writer.writerow([
            ev.event_id,
            ev.contact_id,
            contact.email if contact else "",
            f"{contact.first_name} {contact.last_name}" if contact else "",
            ev.step_id,
            ev.variant_index,
            ev.subject or "",
            ev.sent_at.isoformat() if ev.sent_at else "",
            ev.opened_at.isoformat() if ev.opened_at else "",
            ev.clicked_at.isoformat() if ev.clicked_at else "",
            ev.reply_detected_at.isoformat() if ev.reply_detected_at else "",
            ev.status.value if ev.status else "",
        ])

    from starlette.responses import StreamingResponse
    output.seek(0)
    filename = f"campaign_{campaign_id}_analytics.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ─── Campaign Health Score ────────────────────────────────────────

@router.get("/{campaign_id}/health")
def get_campaign_health(
    campaign_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Get detailed health score breakdown for a campaign."""
    campaign = db.query(Campaign).filter(Campaign.campaign_id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if tenant_id is not None and campaign.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Campaign not found")

    from app.services.campaign_health import calculate_campaign_health
    return calculate_campaign_health(campaign_id, db)


# ─── Campaign Comparison ─────────────────────────────────────────

@router.post("/compare")
def compare_campaigns(
    request: Request,
    body: dict,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Compare multiple campaigns side-by-side. Body: {"campaign_ids": [1, 2, 3]}"""
    campaign_ids = body.get("campaign_ids", [])
    if not campaign_ids or len(campaign_ids) < 2:
        raise HTTPException(status_code=400, detail="Provide at least 2 campaign_ids")
    if len(campaign_ids) > 10:
        raise HTTPException(status_code=400, detail="Maximum 10 campaigns for comparison")

    from app.db.models.outreach import OutreachEvent, OutreachStatus

    comparisons = []
    for cid in campaign_ids:
        campaign = db.query(Campaign).filter(Campaign.campaign_id == cid).first()
        if not campaign:
            continue
        if tenant_id is not None and campaign.tenant_id != tenant_id:
            continue

        total_sent = db.query(OutreachEvent).filter(
            OutreachEvent.campaign_id == cid,
            OutreachEvent.status == OutreachStatus.SENT,
        ).count()
        total_opened = db.query(OutreachEvent).filter(
            OutreachEvent.campaign_id == cid,
            OutreachEvent.opened_at.isnot(None),
        ).count()
        total_clicked = db.query(OutreachEvent).filter(
            OutreachEvent.campaign_id == cid,
            OutreachEvent.clicked_at.isnot(None),
        ).count()
        total_replied = db.query(CampaignContact).filter(
            CampaignContact.campaign_id == cid,
            CampaignContact.status == CampaignContactStatus.REPLIED,
        ).count()
        total_bounced = db.query(CampaignContact).filter(
            CampaignContact.campaign_id == cid,
            CampaignContact.status == CampaignContactStatus.BOUNCED,
        ).count()
        total_contacts = db.query(CampaignContact).filter(
            CampaignContact.campaign_id == cid,
        ).count()

        steps_count = db.query(SequenceStep).filter(
            SequenceStep.campaign_id == cid,
        ).count()

        comparisons.append({
            "campaign_id": cid,
            "name": campaign.name,
            "status": campaign.status.value if campaign.status else "draft",
            "total_contacts": total_contacts,
            "total_sent": total_sent,
            "total_opened": total_opened,
            "open_rate": round(total_opened / total_sent * 100, 1) if total_sent > 0 else 0,
            "total_clicked": total_clicked,
            "click_rate": round(total_clicked / total_sent * 100, 1) if total_sent > 0 else 0,
            "total_replied": total_replied,
            "reply_rate": round(total_replied / total_contacts * 100, 1) if total_contacts > 0 else 0,
            "total_bounced": total_bounced,
            "bounce_rate": round(total_bounced / total_contacts * 100, 1) if total_contacts > 0 else 0,
            "steps_count": steps_count,
            "daily_limit": campaign.daily_limit,
            "created_at": campaign.created_at.isoformat() if hasattr(campaign, 'created_at') and campaign.created_at else None,
        })

    return {"campaigns": comparisons, "count": len(comparisons)}


# ─── A/B Test Stats & Auto-Optimize ──────────────────────────────

@router.get("/{campaign_id}/steps/{step_id}/ab-stats")
def get_ab_test_stats(
    campaign_id: int,
    step_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR, UserRole.VIEWER])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Get A/B test variant statistics for a step."""
    campaign = db.query(Campaign).filter(Campaign.campaign_id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if tenant_id is not None and campaign.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Campaign not found")

    from app.services.ab_optimizer import get_variant_stats
    stats = get_variant_stats(step_id, db)
    return {"step_id": step_id, "variants": stats}


@router.post("/{campaign_id}/steps/{step_id}/ab-optimize")
def trigger_ab_optimize(
    campaign_id: int,
    step_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Manually trigger A/B test optimization for a step."""
    campaign = db.query(Campaign).filter(Campaign.campaign_id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if tenant_id is not None and campaign.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Campaign not found")

    from app.services.ab_optimizer import auto_optimize
    result = auto_optimize(step_id, db)
    return result


# ─── Duplicate ─────────────────────────────────────────────────────

@router.post("/{campaign_id}/duplicate")
@limiter.limit("10/hour")
def duplicate_campaign(
    request: Request,
    campaign_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    original = db.query(Campaign).filter(Campaign.campaign_id == campaign_id).first()
    if not original:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if tenant_id is not None and original.tenant_id != tenant_id:
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
        tenant_id=original.tenant_id,
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


# ─── Campaign Activity Feed ──────────────────────────────────────

@router.get("/{campaign_id}/activity")
def get_campaign_activity(
    campaign_id: int,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    event_type: Optional[str] = Query(None, description="Filter: sent/opened/clicked/replied/bounced"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Real-time activity feed for a campaign."""
    campaign = db.query(Campaign).filter(Campaign.campaign_id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if tenant_id is not None and campaign.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Campaign not found")

    from app.db.models.outreach import OutreachEvent, OutreachStatus
    from app.db.models.contact import ContactDetails

    query = db.query(OutreachEvent).filter(OutreachEvent.campaign_id == campaign_id)

    # Filter by event type
    if event_type == "bounced":
        query = query.filter(OutreachEvent.status == OutreachStatus.BOUNCED)
    elif event_type == "replied":
        query = query.filter(OutreachEvent.reply_detected_at.isnot(None))
    elif event_type == "clicked":
        query = query.filter(OutreachEvent.clicked_at.isnot(None))
    elif event_type == "opened":
        query = query.filter(OutreachEvent.opened_at.isnot(None))
    elif event_type == "sent":
        query = query.filter(OutreachEvent.status == OutreachStatus.SENT)

    total = query.count()
    events = query.order_by(OutreachEvent.sent_at.desc()).offset(offset).limit(limit).all()

    items = []
    for ev in events:
        contact = db.query(ContactDetails).filter(
            ContactDetails.contact_id == ev.contact_id
        ).first()

        # Determine event type
        if ev.status == OutreachStatus.BOUNCED:
            ev_type = "bounced"
        elif ev.reply_detected_at:
            ev_type = "replied"
        elif ev.clicked_at:
            ev_type = "clicked"
        elif ev.opened_at:
            ev_type = "opened"
        else:
            ev_type = "sent"

        # Best timestamp for this event type
        timestamp = ev.reply_detected_at or ev.clicked_at or ev.opened_at or ev.sent_at

        items.append({
            "event_id": ev.event_id,
            "contact_email": contact.email if contact else "",
            "contact_name": f"{contact.first_name} {contact.last_name}" if contact else f"Contact #{ev.contact_id}",
            "event_type": ev_type,
            "timestamp": timestamp.isoformat() if timestamp else None,
            "step_order": ev.step_id,
            "variant_index": ev.variant_index,
            "subject": ev.subject or "",
        })

    return {"items": items, "total": total, "limit": limit, "offset": offset}


# ─── Email Thread Preview ────────────────────────────────────────

@router.get("/{campaign_id}/thread-preview")
def get_thread_preview(
    campaign_id: int,
    contact_id: int = Query(..., description="Contact ID to preview thread for"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Preview the full email thread as it would be sent to a specific contact."""
    campaign = db.query(Campaign).filter(Campaign.campaign_id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if tenant_id is not None and campaign.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Campaign not found")

    from app.db.models.contact import ContactDetails
    from app.db.models.lead import LeadDetails

    contact = db.query(ContactDetails).filter(ContactDetails.contact_id == contact_id).first()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    steps = db.query(SequenceStep).filter(
        SequenceStep.campaign_id == campaign_id
    ).order_by(SequenceStep.step_order).all()

    # Build placeholder context
    lead = None
    cc = db.query(CampaignContact).filter(
        CampaignContact.campaign_id == campaign_id,
        CampaignContact.contact_id == contact_id,
    ).first()
    if cc and cc.lead_id:
        lead = db.query(LeadDetails).filter(LeadDetails.lead_id == cc.lead_id).first()

    placeholders = {
        "first_name": contact.first_name or "",
        "last_name": contact.last_name or "",
        "email": contact.email or "",
        "company": contact.client_name or "",
        "job_title": contact.title or "",
        "city": getattr(lead, "city", "") or "" if lead else "",
        "state": getattr(lead, "state", "") or "" if lead else "",
    }

    preview_steps = []
    for step in steps:
        step_data = {
            "step_order": step.step_order,
            "step_type": step.step_type.value if step.step_type else "email",
            "delay_days": step.delay_days,
            "delay_hours": step.delay_hours,
        }

        if step.step_type and step.step_type.value == "email":
            subject = step.subject or ""
            body = step.body_html or ""

            # Apply variant selection if A/B test
            if step.variants_json:
                try:
                    variants = json.loads(step.variants_json)
                    if variants and len(variants) > 0:
                        # Use first variant for preview
                        variant = variants[0]
                        subject = variant.get("subject", subject)
                        body = variant.get("body_html", body)
                except (json.JSONDecodeError, TypeError):
                    pass

            # Apply placeholders
            for key, val in placeholders.items():
                subject = subject.replace("{{" + key + "}}", val)
                body = body.replace("{{" + key + "}}", val)

            step_data["subject"] = subject
            step_data["body_html"] = body
        elif step.step_type and step.step_type.value == "condition":
            step_data["condition_type"] = step.condition_type
            step_data["condition_window_hours"] = step.condition_window_hours
        elif step.step_type and step.step_type.value == "wait":
            pass  # delay_days/hours already included

        preview_steps.append(step_data)

    return {
        "campaign_id": campaign_id,
        "contact_id": contact_id,
        "contact_name": f"{contact.first_name} {contact.last_name}",
        "steps": preview_steps,
    }
