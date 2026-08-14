"""Email template management endpoints."""
import html
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_role, get_current_tenant_id
from app.db.models.user import User, UserRole
from app.db.models.email_template import EmailTemplate, TemplateStatus, TemplateCategory
from app.schemas.email_template import (
    EmailTemplateCreate,
    EmailTemplateUpdate,
    EmailTemplateResponse,
    EmailTemplateListResponse,
)

router = APIRouter(prefix="/templates", tags=["Email Templates"])

# ─── Goal → Category auto-derivation ────────────────────────────────────────

GOAL_TO_CATEGORY = {
    "cold_outreach": TemplateCategory.OUTREACH,
    "demo_request": TemplateCategory.OUTREACH,
    "event_invite": TemplateCategory.OUTREACH,
    "follow_up": TemplateCategory.FOLLOWUP,
    "re_engagement": TemplateCategory.FOLLOWUP,
}


def _derive_category(goal: Optional[str], fallback: TemplateCategory) -> TemplateCategory:
    """Derive category from goal if possible, otherwise use fallback."""
    if goal and goal in GOAL_TO_CATEGORY:
        return GOAL_TO_CATEGORY[goal]
    return fallback


# ─── Scorecard request schemas ──────────────────────────────────────────────

class TemplateScoreRequest(BaseModel):
    subject: str
    body_html: str
    body_text: Optional[str] = ""

class ApplyFixesRequest(BaseModel):
    subject: str
    body_html: str
    body_text: Optional[str] = ""
    fix_ids: List[str]


# ─── Scorecard endpoints ────────────────────────────────────────────────────

@router.post("/score")
async def score_template_endpoint(
    data: TemplateScoreRequest,
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.BDM])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Compute 10-dimension scorecard for template content."""
    from app.services.template_scorer import score_template
    return score_template(data.subject, data.body_html, data.body_text or "")


@router.post("/fixes")
async def get_template_fixes_endpoint(
    data: TemplateScoreRequest,
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.BDM])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Get fix suggestions for template content."""
    from app.services.template_scorer import get_fixes
    return get_fixes(data.subject, data.body_html, data.body_text or "")


@router.post("/apply-fixes")
async def apply_template_fixes_endpoint(
    data: ApplyFixesRequest,
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.BDM])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Apply selected fixes and return updated content + before/after scores."""
    from app.services.template_scorer import apply_fixes
    return apply_fixes(data.subject, data.body_html, data.body_text or "", data.fix_ids)


@router.get("", response_model=EmailTemplateListResponse)
async def list_templates(
    show_archived: bool = False,
    industry: Optional[str] = Query(None, description="Filter by industry"),
    goal: Optional[str] = Query(None, description="Filter by goal"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status (active/inactive)"),
    search: Optional[str] = Query(None, description="Search by name or subject"),
    sort_by: Optional[str] = Query(None, description="Column to sort by"),
    sort_order: Optional[str] = Query("desc", description="Sort order: asc or desc"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.BDM])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """List all email templates. Always scoped to one tenant (super admin defaults to own tenant)."""
    effective_tenant = tenant_id or current_user.tenant_id or 1
    query = db.query(EmailTemplate)
    query = query.filter(EmailTemplate.tenant_id == effective_tenant)
    if show_archived:
        query = query.filter(EmailTemplate.is_archived == True)
    else:
        query = query.filter(EmailTemplate.is_archived == False)
    if industry:
        query = query.filter(EmailTemplate.industry == industry)
    if goal:
        query = query.filter(EmailTemplate.goal == goal)
    if status_filter:
        query = query.filter(EmailTemplate.status == status_filter)
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            (EmailTemplate.name.ilike(search_term)) | (EmailTemplate.subject.ilike(search_term))
        )

    # Sorting
    SORT_COLUMNS = {
        "name": EmailTemplate.name,
        "category": EmailTemplate.category,
        "goal": EmailTemplate.goal,
        "industry": EmailTemplate.industry,
        "subject": EmailTemplate.subject,
        "status": EmailTemplate.status,
        "created_at": EmailTemplate.created_at,
    }
    if sort_by and sort_by in SORT_COLUMNS:
        col = SORT_COLUMNS[sort_by]
        order_col = col.asc() if sort_order == "asc" else col.desc()
        templates = query.order_by(order_col).all()
    else:
        # Default: active first, then by created_at desc
        from sqlalchemy import case
        status_priority = case(
            (EmailTemplate.status == TemplateStatus.ACTIVE, 0),
            else_=1,
        )
        templates = query.order_by(status_priority, EmailTemplate.created_at.desc()).all()

    # Find active template per category
    active_outreach = next(
        (t for t in templates if t.status == TemplateStatus.ACTIVE and t.category == TemplateCategory.OUTREACH), None
    )
    active_followup = next(
        (t for t in templates if t.status == TemplateStatus.ACTIVE and t.category == TemplateCategory.FOLLOWUP), None
    )
    # Backward compat: active_template_id = first active found (outreach preferred)
    active_any = active_outreach or active_followup

    return EmailTemplateListResponse(
        items=[EmailTemplateResponse.model_validate(t) for t in templates],
        total=len(templates),
        active_template_id=active_any.template_id if active_any else None,
        active_outreach_template_id=active_outreach.template_id if active_outreach else None,
        active_followup_template_id=active_followup.template_id if active_followup else None,
    )


@router.get("/active", response_model=Optional[EmailTemplateResponse])
async def get_active_template(
    category: Optional[TemplateCategory] = Query(None, description="Filter by category"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.BDM])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Get the currently active email template. Optionally filter by category."""
    effective_tenant = tenant_id or current_user.tenant_id or 1
    query = db.query(EmailTemplate).filter(
        EmailTemplate.tenant_id == effective_tenant,
        EmailTemplate.status == TemplateStatus.ACTIVE,
    )
    if category:
        query = query.filter(EmailTemplate.category == category)
    template = query.first()
    if not template:
        return None
    return EmailTemplateResponse.model_validate(template)


@router.get("/{template_id}", response_model=EmailTemplateResponse)
async def get_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.BDM])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Get a single email template by ID."""
    template = db.query(EmailTemplate).filter(
        EmailTemplate.template_id == template_id
    ).first()
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found",
        )
    # Verify tenant ownership
    if tenant_id is not None and template.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found",
        )
    return EmailTemplateResponse.model_validate(template)


@router.post("", response_model=EmailTemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_template(
    template_in: EmailTemplateCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Create a new email template."""
    effective_tenant = tenant_id or 1

    # Auto-derive category from goal
    template_in.category = _derive_category(template_in.goal, template_in.category)

    # If creating as active, deactivate others in the SAME CATEGORY
    if template_in.status == TemplateStatus.ACTIVE:
        db.query(EmailTemplate).filter(
            EmailTemplate.tenant_id == effective_tenant,
            EmailTemplate.status == TemplateStatus.ACTIVE,
            EmailTemplate.category == template_in.category,
        ).update({"status": TemplateStatus.INACTIVE})

    template = EmailTemplate(**template_in.model_dump())
    template.tenant_id = effective_tenant
    db.add(template)
    db.commit()
    db.refresh(template)
    return EmailTemplateResponse.model_validate(template)


@router.put("/{template_id}", response_model=EmailTemplateResponse)
async def update_template(
    template_id: int,
    template_in: EmailTemplateUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Update an email template."""
    template = db.query(EmailTemplate).filter(
        EmailTemplate.template_id == template_id
    ).first()
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found",
        )

    # Verify tenant ownership
    if tenant_id is not None and template.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found",
        )

    update_data = template_in.model_dump(exclude_unset=True)

    # Auto-derive category from goal if goal is being updated
    if "goal" in update_data:
        current_category = update_data.get("category", template.category)
        derived = _derive_category(update_data["goal"], current_category)
        update_data["category"] = derived

    # If setting to active, deactivate others in the SAME CATEGORY
    if update_data.get("status") == TemplateStatus.ACTIVE:
        # Use the new category if being changed, otherwise the existing one
        effective_category = update_data.get("category", template.category)
        db.query(EmailTemplate).filter(
            EmailTemplate.tenant_id == template.tenant_id,
            EmailTemplate.status == TemplateStatus.ACTIVE,
            EmailTemplate.category == effective_category,
            EmailTemplate.template_id != template_id,
        ).update({"status": TemplateStatus.INACTIVE})

    for field, value in update_data.items():
        setattr(template, field, value)

    db.commit()
    db.refresh(template)
    return EmailTemplateResponse.model_validate(template)


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Archive an email template (soft delete). Cannot archive the default template."""
    template = db.query(EmailTemplate).filter(
        EmailTemplate.template_id == template_id
    ).first()
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found",
        )

    # Verify tenant ownership
    if tenant_id is not None and template.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found",
        )

    if template.is_default:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete the default template",
        )
    # Soft delete: archive instead of hard deleting
    template.is_archived = True
    template.status = TemplateStatus.INACTIVE
    db.commit()


@router.post("/{template_id}/activate", response_model=EmailTemplateResponse)
async def activate_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Activate a template (deactivates others in the same category)."""
    template = db.query(EmailTemplate).filter(
        EmailTemplate.template_id == template_id
    ).first()
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found",
        )

    # Verify tenant ownership
    if tenant_id is not None and template.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found",
        )

    # Deactivate others in the SAME CATEGORY within the same tenant
    db.query(EmailTemplate).filter(
        EmailTemplate.tenant_id == template.tenant_id,
        EmailTemplate.status == TemplateStatus.ACTIVE,
        EmailTemplate.category == template.category,
    ).update({"status": TemplateStatus.INACTIVE})

    template.status = TemplateStatus.ACTIVE
    db.commit()
    db.refresh(template)
    return EmailTemplateResponse.model_validate(template)


@router.post("/{template_id}/preview")
async def preview_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.BDM])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Preview a template with sample data."""
    template = db.query(EmailTemplate).filter(
        EmailTemplate.template_id == template_id
    ).first()
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found",
        )

    # Verify tenant ownership
    if tenant_id is not None and template.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found",
        )

    sample_data = {
        "{{contact_first_name}}": "John",
        "{{sender_first_name}}": "Sarah",
        "{{job_title}}": "Senior Software Engineer",
        "{{job_location}}": "New York, NY",
        "{{company_name}}": "Acme Corp",
        "{{signature}}": "<div style='margin-top:20px;padding-top:12px;border-top:1px solid #ccc;font-family:Arial,sans-serif;'><strong>Sarah Smith</strong><br>Recruitment Specialist<br>Exzelon Inc.</div>",
        "{{logo_url}}": "https://www.exzelon.com/gallery/logo.png",
    }

    preview_subject = template.subject
    preview_html = template.body_html
    preview_text = template.body_text or ""

    for placeholder, value in sample_data.items():
        safe_value = html.escape(value)
        preview_subject = preview_subject.replace(placeholder, safe_value)
        preview_html = preview_html.replace(placeholder, value)  # HTML body keeps original (templates are HTML)
        preview_text = preview_text.replace(placeholder, safe_value)

    return {
        "template_id": template.template_id,
        "name": template.name,
        "subject": preview_subject,
        "body_html": preview_html,
        "body_text": preview_text,
        "placeholders_used": list(sample_data.keys()),
    }


@router.post("/{template_id}/duplicate", response_model=EmailTemplateResponse, status_code=status.HTTP_201_CREATED)
async def duplicate_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Duplicate an email template."""
    template = db.query(EmailTemplate).filter(
        EmailTemplate.template_id == template_id
    ).first()
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found",
        )

    # Verify tenant ownership
    if tenant_id is not None and template.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found",
        )

    new_template = EmailTemplate(
        name=f"{template.name} (Copy)",
        subject=template.subject,
        body_html=template.body_html,
        body_text=template.body_text,
        status=TemplateStatus.INACTIVE,
        category=template.category,
        is_default=False,
        description=template.description,
        tenant_id=tenant_id or 1,
    )
    db.add(new_template)
    db.commit()
    db.refresh(new_template)
    return EmailTemplateResponse.model_validate(new_template)


@router.post("/seed-library")
async def seed_template_library(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Seed 12 system templates into the library (super_admin only)."""
    effective_tenant = tenant_id or current_user.tenant_id or 1

    # Check if system templates already exist for this tenant
    existing_system = db.query(EmailTemplate).filter(
        EmailTemplate.tenant_id == effective_tenant,
        EmailTemplate.is_system == True,
    ).count()
    if existing_system >= 12:
        return {"message": "System templates already seeded", "count": existing_system}

    system_templates = [
        {"name": "Cold Outreach - Staffing", "subject": "Candidates ready for your {{job_title}} role", "industry": "staffing", "goal": "intro", "category": "outreach",
         "body_html": "<p>Hi {{contact_first_name}},</p><p>I noticed {{company_name}} is hiring for {{job_title}}. We have pre-screened candidates ready for review.</p><p>Would a quick call work this week?</p>"},
        {"name": "Cold Outreach - Healthcare", "subject": "Healthcare talent for {{company_name}}", "industry": "healthcare", "goal": "intro", "category": "outreach",
         "body_html": "<p>Hi {{contact_first_name}},</p><p>{{company_name}} has an opening for {{job_title}}. We specialize in healthcare staffing and can deliver qualified candidates within 48 hours.</p><p>Interested in a free candidate preview?</p>"},
        {"name": "Cold Outreach - Technology", "subject": "Top tech talent for {{job_title}}", "industry": "technology", "goal": "intro", "category": "outreach",
         "body_html": "<p>Hi {{contact_first_name}},</p><p>I see {{company_name}} is looking for a {{job_title}}. Our tech recruiting team has candidates with the exact skill set you need.</p><p>Can I send over a few profiles?</p>"},
        {"name": "Cold Outreach - Manufacturing", "subject": "Skilled workers for {{company_name}}", "industry": "manufacturing", "goal": "intro", "category": "outreach",
         "body_html": "<p>Hi {{contact_first_name}},</p><p>{{company_name}} posted a {{job_title}} position. We staff manufacturing roles nationwide and can help fill it fast.</p><p>Want to see some candidates?</p>"},
        {"name": "Follow-up - Gentle Bump", "subject": "Quick follow-up — {{job_title}}", "industry": None, "goal": "followup", "category": "followup",
         "body_html": "<p>Hi {{contact_first_name}},</p><p>Just following up on my previous email about the {{job_title}} role. I understand you are busy — happy to work around your schedule.</p><p>Would a brief 10-minute call work?</p>"},
        {"name": "Follow-up - Value Add", "subject": "Market insights for {{job_title}} hiring", "industry": None, "goal": "followup", "category": "followup",
         "body_html": "<p>Hi {{contact_first_name}},</p><p>Since my last email, I wanted to share that we are seeing strong candidate availability for {{job_title}} roles in your area. Average time-to-fill is down 15% this quarter.</p><p>Happy to share more details on a quick call.</p>"},
        {"name": "Follow-up - Case Study", "subject": "How we helped a company like {{company_name}}", "industry": None, "goal": "followup", "category": "followup",
         "body_html": "<p>Hi {{contact_first_name}},</p><p>A company similar to {{company_name}} recently used our services to fill their {{job_title}} position in under 2 weeks — with zero recruiter fees upfront.</p><p>Would you like to learn how?</p>"},
        {"name": "Re-engagement - Past Contact", "subject": "Still looking for {{job_title}} talent?", "industry": None, "goal": "re-engage", "category": "outreach",
         "body_html": "<p>Hi {{contact_first_name}},</p><p>We connected a while back about staffing needs at {{company_name}}. I wanted to check in — are you still looking for {{job_title}} candidates?</p><p>We have several new profiles that might be a great fit.</p>"},
        {"name": "Meeting Request", "subject": "15 min to discuss {{company_name}} hiring", "industry": None, "goal": "meeting", "category": "outreach",
         "body_html": "<p>Hi {{contact_first_name}},</p><p>I would love to spend 15 minutes discussing how we can help {{company_name}} with your {{job_title}} search. No commitment — just a quick chat to see if we are a good fit.</p><p>What does your calendar look like this week?</p>"},
        {"name": "Referral Request", "subject": "Quick question about hiring at {{company_name}}", "industry": None, "goal": "referral", "category": "outreach",
         "body_html": "<p>Hi {{contact_first_name}},</p><p>I am reaching out about the {{job_title}} opening at {{company_name}}. If you are not the right person to speak with, could you point me to whoever handles recruiting for this role?</p><p>Thanks in advance!</p>"},
        {"name": "Breakup Email", "subject": "Last attempt — {{job_title}} at {{company_name}}", "industry": None, "goal": "breakup", "category": "followup",
         "body_html": "<p>Hi {{contact_first_name}},</p><p>I have reached out a few times about the {{job_title}} position and haven't heard back, so I will assume the timing isn't right.</p><p>If things change, feel free to reach out anytime. Wishing you success in your search!</p>"},
        {"name": "Event/Season Trigger", "subject": "New year hiring plans for {{company_name}}?", "industry": None, "goal": "seasonal", "category": "outreach",
         "body_html": "<p>Hi {{contact_first_name}},</p><p>As we head into the new quarter, many companies are ramping up hiring. If {{company_name}} has any upcoming {{job_title}} needs, we would love to help you get a head start.</p><p>Want to chat this week?</p>"},
    ]

    created = 0
    for tmpl in system_templates:
        # Skip if a system template with same name already exists
        exists = db.query(EmailTemplate).filter(
            EmailTemplate.tenant_id == effective_tenant,
            EmailTemplate.name == tmpl["name"],
            EmailTemplate.is_system == True,
        ).first()
        if exists:
            continue

        cat = TemplateCategory.FOLLOWUP if tmpl["category"] == "followup" else TemplateCategory.OUTREACH
        template = EmailTemplate(
            tenant_id=effective_tenant,
            name=tmpl["name"],
            subject=tmpl["subject"],
            body_html=tmpl["body_html"],
            body_text="",
            status=TemplateStatus.INACTIVE,
            category=cat,
            is_default=False,
            is_system=True,
            industry=tmpl.get("industry"),
            goal=tmpl.get("goal"),
            description=f"System template: {tmpl['goal']}",
        )
        db.add(template)
        created += 1

    db.commit()
    return {"message": f"Seeded {created} system templates", "count": created}


@router.post("/{template_id}/import-to-step")
async def import_template_to_step(
    template_id: int,
    step_id: int = Query(..., description="Target sequence step ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.BDM])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Copy template content to a campaign sequence step."""
    template = db.query(EmailTemplate).filter(
        EmailTemplate.template_id == template_id
    ).first()
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found",
        )
    # Verify tenant ownership
    if tenant_id is not None and template.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found",
        )

    from app.db.models.campaign import SequenceStep
    step = db.query(SequenceStep).filter(
        SequenceStep.step_id == step_id,
    ).first()
    if not step:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sequence step not found",
        )

    step.subject = template.subject
    step.body_html = template.body_html
    step.body_text = template.body_text
    step.template_id = template.template_id
    db.commit()

    return {
        "message": "Template imported to step",
        "step_id": step.step_id,
        "template_id": template.template_id,
    }
