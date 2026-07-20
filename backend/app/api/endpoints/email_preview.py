"""Email Preview & Approve API endpoints."""
import json
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import func as sa_func

from app.api.deps.database import get_db
from app.api.deps.auth import get_current_active_user, require_role, get_current_tenant_id
from app.core.rate_limiter import limiter
from app.db.query_helpers import tenant_filter
from app.db.models.user import User, UserRole
from app.db.models.outreach_draft import OutreachDraft, DraftStatus
from app.db.models.contact import ContactDetails
from app.db.models.lead import LeadDetails
from app.db.models.sender_mailbox import SenderMailbox
from app.db.models.campaign import Campaign, SequenceStep, CampaignContact

router = APIRouter(prefix="/email-preview", tags=["email-preview"])


# ─── Schemas ───────────────────────────────────────────────────────

class GenerateDraftsRequest(BaseModel):
    source: str = Field(..., description="campaign, pipeline, or broadcast")
    campaign_id: Optional[int] = None
    step_index: Optional[int] = None
    template_id: Optional[int] = None
    mailbox_id: Optional[int] = None
    contact_ids: Optional[List[int]] = None
    limit: int = 30

class UpdateDraftRequest(BaseModel):
    subject: Optional[str] = None
    body_html: Optional[str] = None
    body_text: Optional[str] = None
    mailbox_id: Optional[int] = None

class ApproveAllRequest(BaseModel):
    batch_id: str

class BulkDraftIdsRequest(BaseModel):
    draft_ids: List[int]

class BulkDeleteDraftsRequest(BaseModel):
    draft_ids: List[int]

class SendBatchRequest(BaseModel):
    batch_id: str

class DeliverabilityRequest(BaseModel):
    mailbox_id: int
    subject: str
    body_html: str

class SpamCheckRequest(BaseModel):
    subject: str
    body_html: str

class PreviewPersonalizationRequest(BaseModel):
    campaign_id: int
    step_index: int = 0
    contact_ids: Optional[List[int]] = None

class SpamFixRequest(BaseModel):
    replacements: List[dict] = Field(..., description="List of {original, replacement}")


# ─── Endpoints ─────────────────────────────────────────────────────

@router.post("/generate")
@limiter.limit("10/hour")
def generate_drafts(
    request: Request,
    data: GenerateDraftsRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Generate preview drafts from campaign, pipeline, or broadcast."""
    from app.services.email_preview_service import (
        generate_campaign_drafts, generate_pipeline_drafts, generate_broadcast_drafts,
    )

    tid = tenant_id or 1
    source = data.source.lower()

    if source == "campaign":
        if not data.campaign_id or data.step_index is None:
            raise HTTPException(400, "campaign_id and step_index required for campaign source")
        result = generate_campaign_drafts(data.campaign_id, data.step_index, db, tid)
    elif source == "pipeline":
        result = generate_pipeline_drafts(tid, data.limit, db)
    elif source == "broadcast":
        if not data.contact_ids or not data.template_id or not data.mailbox_id:
            raise HTTPException(400, "contact_ids, template_id, and mailbox_id required for broadcast source")
        result = generate_broadcast_drafts(data.contact_ids, data.template_id, data.mailbox_id, db, tid)
    else:
        raise HTTPException(400, f"Invalid source: {source}. Must be campaign, pipeline, or broadcast")

    if result.get("error"):
        raise HTTPException(400, result["error"])

    return result


@router.get("/drafts")
def list_drafts(
    batch_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    campaign_id: Optional[List[int]] = Query(None),
    mailbox_id: Optional[List[int]] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """List drafts with filters."""
    query = tenant_filter(db.query(OutreachDraft), OutreachDraft, tenant_id)

    if batch_id:
        query = query.filter(OutreachDraft.batch_id == batch_id)
    if status:
        query = query.filter(OutreachDraft.status == status)
    if source:
        query = query.filter(OutreachDraft.source == source)
    if campaign_id:
        query = query.filter(OutreachDraft.campaign_id.in_(campaign_id))
    if mailbox_id:
        query = query.filter(OutreachDraft.mailbox_id.in_(mailbox_id))

    query = query.filter(OutreachDraft.is_archived == False)

    total = query.count()
    drafts = query.order_by(OutreachDraft.created_at.desc()).offset(
        (page - 1) * per_page
    ).limit(per_page).all()

    # Compute status counts from the FULL filtered query (not just current page)
    base_query = tenant_filter(db.query(OutreachDraft), OutreachDraft, tenant_id)
    base_query = base_query.filter(OutreachDraft.is_archived == False)
    if batch_id:
        base_query = base_query.filter(OutreachDraft.batch_id == batch_id)
    if source:
        base_query = base_query.filter(OutreachDraft.source == source)
    if campaign_id:
        base_query = base_query.filter(OutreachDraft.campaign_id == campaign_id)
    if mailbox_id:
        base_query = base_query.filter(OutreachDraft.mailbox_id == mailbox_id)
    status_counts = dict(
        base_query.with_entities(OutreachDraft.status, sa_func.count())
        .group_by(OutreachDraft.status).all()
    )

    return {
        "drafts": [_draft_to_dict(d, db) for d in drafts],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
        "pending_count": status_counts.get("pending", 0),
        "approved_count": status_counts.get("approved", 0),
        "sent_count": status_counts.get("sent", 0),
        "rejected_count": status_counts.get("rejected", 0),
    }


@router.get("/drafts/{draft_id}")
def get_draft(
    draft_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Get a single draft with contact and lead info."""
    draft = db.query(OutreachDraft).filter(
        OutreachDraft.draft_id == draft_id,
    ).first()
    if not draft:
        raise HTTPException(404, "Draft not found")
    if tenant_id is not None and draft.tenant_id != tenant_id:
        raise HTTPException(404, "Draft not found")

    return _draft_to_dict(draft, db, include_details=True)


@router.put("/drafts/{draft_id}")
def update_draft(
    draft_id: int,
    data: UpdateDraftRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Edit draft content manually."""
    from app.services.spam_checker import check_spam_score

    draft = db.query(OutreachDraft).filter(
        OutreachDraft.draft_id == draft_id,
    ).first()
    if not draft:
        raise HTTPException(404, "Draft not found")
    if tenant_id is not None and draft.tenant_id != tenant_id:
        raise HTTPException(404, "Draft not found")

    if data.subject is not None:
        draft.subject = data.subject
    if data.body_html is not None:
        draft.body_html = data.body_html
    if data.body_text is not None:
        draft.body_text = data.body_text
    if data.mailbox_id is not None:
        draft.mailbox_id = data.mailbox_id

    # Re-run spam check on content changes
    if data.subject is not None or data.body_html is not None:
        spam_result = check_spam_score(draft.subject, draft.body_html)
        draft.spam_score = spam_result["score"]
        draft.spam_grade = spam_result["grade"]
        draft.flagged_words_json = json.dumps(spam_result["flagged_words"])

    db.commit()
    db.refresh(draft)
    return _draft_to_dict(draft, db)


@router.post("/drafts/{draft_id}/approve")
def approve_single_draft(
    draft_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Approve a single draft."""
    from app.services.email_preview_service import approve_draft
    result = approve_draft(draft_id, user.user_id, db, tenant_id or 1)
    if result.get("error"):
        raise HTTPException(400, result["error"])
    return result


@router.post("/drafts/{draft_id}/reject")
def reject_single_draft(
    draft_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Reject a single draft."""
    from app.services.email_preview_service import reject_draft
    result = reject_draft(draft_id, user.user_id, db, tenant_id or 1)
    if result.get("error"):
        raise HTTPException(400, result["error"])
    return result


@router.post("/drafts/approve-all")
def approve_all_drafts(
    data: ApproveAllRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Bulk approve all pending drafts in a batch."""
    from app.services.email_preview_service import approve_batch
    result = approve_batch(data.batch_id, user.user_id, db, tenant_id or 1)
    return result


@router.post("/drafts/bulk-approve")
def bulk_approve_drafts(
    data: BulkDraftIdsRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Approve multiple drafts by ID list."""
    if not data.draft_ids:
        raise HTTPException(400, "No draft IDs provided")
    effective_tenant = tenant_id or 1
    from datetime import datetime
    now = datetime.utcnow()
    count = db.query(OutreachDraft).filter(
        OutreachDraft.draft_id.in_(data.draft_ids),
        OutreachDraft.tenant_id == effective_tenant,
        OutreachDraft.status == DraftStatus.PENDING,
    ).update(
        {"status": DraftStatus.APPROVED, "approved_by": user.user_id, "approved_at": now},
        synchronize_session=False,
    )
    db.commit()
    return {"approved_count": count}


@router.post("/drafts/approve-all-pending")
def approve_all_pending_drafts(
    db: Session = Depends(get_db),
    user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Approve ALL pending drafts for the tenant (no batch_id required)."""
    effective_tenant = tenant_id or 1
    from datetime import datetime
    now = datetime.utcnow()
    count = db.query(OutreachDraft).filter(
        OutreachDraft.tenant_id == effective_tenant,
        OutreachDraft.status == DraftStatus.PENDING,
    ).update(
        {"status": DraftStatus.APPROVED, "approved_by": user.user_id, "approved_at": now},
        synchronize_session=False,
    )
    db.commit()
    return {"approved_count": count}


@router.post("/drafts/bulk-send")
def bulk_send_drafts(
    data: BulkDraftIdsRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Send multiple approved drafts by ID list (runs in background)."""
    if not data.draft_ids:
        raise HTTPException(400, "No draft IDs provided")
    from app.services.email_preview_service import send_single_draft
    from app.db.base import SessionLocal

    tid = tenant_id or 1
    ids = list(data.draft_ids)

    def _bg_send():
        _db = SessionLocal()
        try:
            for did in ids:
                send_single_draft(did, _db, tid)
        finally:
            _db.close()

    background_tasks.add_task(_bg_send)
    return {"message": f"Sending {len(ids)} draft(s) in background", "status": "processing"}


@router.post("/drafts/send-all-approved")
def send_all_approved_drafts(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Send ALL approved drafts for the tenant (runs in background)."""
    from app.services.email_preview_service import send_single_draft
    from app.db.base import SessionLocal

    tid = tenant_id or 1
    draft_ids = [
        d.draft_id for d in db.query(OutreachDraft.draft_id).filter(
            OutreachDraft.tenant_id == tid,
            OutreachDraft.status == DraftStatus.APPROVED,
        ).all()
    ]
    if not draft_ids:
        return {"message": "No approved drafts to send", "status": "done", "count": 0}

    def _bg_send():
        _db = SessionLocal()
        try:
            for did in draft_ids:
                send_single_draft(did, _db, tid)
        finally:
            _db.close()

    background_tasks.add_task(_bg_send)
    return {"message": f"Sending {len(draft_ids)} approved draft(s) in background", "status": "processing", "count": len(draft_ids)}


@router.post("/drafts/{draft_id}/send")
def send_draft(
    draft_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Send a single approved draft."""
    from app.services.email_preview_service import send_single_draft
    result = send_single_draft(draft_id, db, tenant_id or 1)
    if result.get("blocked"):
        raise HTTPException(409, detail={
            "message": result["error"],
            "reason_code": result.get("reason_code", "BLOCKED"),
        })
    if result.get("error"):
        raise HTTPException(400, result["error"])
    return result


@router.post("/drafts/send-batch")
@limiter.limit("5/hour")
def send_batch_drafts(
    request: Request,
    data: SendBatchRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Send all approved drafts in a batch (runs in background)."""
    from app.services.email_preview_service import send_batch
    from app.db.base import SessionLocal

    tid = tenant_id or 1
    bid = data.batch_id

    def _bg_send():
        _db = SessionLocal()
        try:
            send_batch(bid, _db, tid)
        finally:
            _db.close()

    background_tasks.add_task(_bg_send)
    return {"message": f"Batch send started for {bid}", "status": "processing"}


@router.post("/drafts/{draft_id}/ai-rewrite")
@limiter.limit("20/hour")
def ai_rewrite(
    request: Request,
    draft_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """AI-rewrite a single draft."""
    from app.services.email_preview_service import ai_rewrite_draft
    result = ai_rewrite_draft(draft_id, db, tenant_id or 1)
    if result.get("error"):
        raise HTTPException(400, result["error"])
    return result


@router.post("/deliverability-score")
def deliverability_score(
    data: DeliverabilityRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Calculate deliverability score for a mailbox + email content."""
    from app.services.email_preview_service import calculate_deliverability_score
    result = calculate_deliverability_score(
        data.mailbox_id, data.subject, data.body_html, db, tenant_id or 1
    )
    return result


@router.post("/spam-check")
def spam_check(
    data: SpamCheckRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Check spam score + get AI suggestions for replacements."""
    from app.services.email_preview_service import check_spam_and_suggest
    result = check_spam_and_suggest(data.subject, data.body_html, db, tenant_id or 1)
    return result


@router.post("/preview-personalization")
@limiter.limit("20/hour")
def preview_personalization(
    request: Request,
    data: PreviewPersonalizationRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Preview AI personalization for a campaign step across multiple contacts."""
    from app.services.ai_personalizer import personalize_email_for_contact
    from app.services.spintax import process_spintax

    tid = tenant_id or 1

    # Load campaign
    campaign = tenant_filter(
        db.query(Campaign), Campaign, tenant_id
    ).filter(Campaign.campaign_id == data.campaign_id).first()
    if not campaign:
        raise HTTPException(404, "Campaign not found")

    # Load step by step_order
    step = db.query(SequenceStep).filter(
        SequenceStep.campaign_id == campaign.campaign_id,
        SequenceStep.step_order == data.step_index,
    ).first()
    if not step:
        raise HTTPException(404, f"Step at index {data.step_index} not found")
    if not step.subject or not step.body_html:
        raise HTTPException(400, "Step has no email content to personalize")

    # Resolve contacts
    if data.contact_ids:
        contacts = db.query(ContactDetails).filter(
            ContactDetails.contact_id.in_(data.contact_ids),
        ).all()
        if tenant_id is not None:
            contacts = [c for c in contacts if c.tenant_id == tid]
    else:
        # Auto-pick first 3 enrolled contacts
        cc_rows = db.query(CampaignContact).filter(
            CampaignContact.campaign_id == campaign.campaign_id,
        ).limit(3).all()
        contact_ids_list = [cc.contact_id for cc in cc_rows]
        contacts = db.query(ContactDetails).filter(
            ContactDetails.contact_id.in_(contact_ids_list),
        ).all() if contact_ids_list else []

    if not contacts:
        raise HTTPException(400, "No contacts found for preview")

    results = []
    for contact in contacts:
        # Load associated lead
        lead = None
        cc_row = db.query(CampaignContact).filter(
            CampaignContact.campaign_id == campaign.campaign_id,
            CampaignContact.contact_id == contact.contact_id,
        ).first()
        if cc_row and cc_row.lead_id:
            lead = db.query(LeadDetails).filter(
                LeadDetails.lead_id == cc_row.lead_id,
            ).first()
        if not lead and contact.lead_id:
            lead = db.query(LeadDetails).filter(
                LeadDetails.lead_id == contact.lead_id,
            ).first()

        # Process spintax
        subject = process_spintax(step.subject or "", seed=contact.contact_id, campaign_id=campaign.campaign_id)
        body_html = process_spintax(step.body_html or "", seed=contact.contact_id, campaign_id=campaign.campaign_id)
        body_text = process_spintax(step.body_text or step.body_html or "", seed=contact.contact_id, campaign_id=campaign.campaign_id)

        # Placeholder substitution
        _job_title = (lead.job_title if lead and lead.job_title else "")
        _job_location = (lead.state if lead and lead.state else "")
        _company = (lead.client_name if lead and lead.client_name else (contact.client_name or ""))
        _placeholders = {
            "{{contact_first_name}}": contact.first_name or "",
            "{{contact_last_name}}": contact.last_name or "",
            "{{company_name}}": _company,
            "{{contact_title}}": contact.title or "",
            "{{job_title}}": _job_title,
            "{{job_location}}": _job_location,
        }
        try:
            from jinja2 import Template as Jinja2Template
            ctx = {
                "contact_first_name": contact.first_name or "",
                "contact_last_name": contact.last_name or "",
                "company_name": _company,
                "contact_title": contact.title or "",
                "job_title": _job_title,
                "job_location": _job_location,
                "contact": {"first_name": contact.first_name or "", "last_name": contact.last_name or "", "title": contact.title or "", "email": contact.email or "", "company": contact.client_name or ""},
                "lead": {"job_title": _job_title, "location": _job_location, "company": _company},
            }
            subject = Jinja2Template(subject).render(**ctx)
            body_html = Jinja2Template(body_html).render(**ctx)
            body_text = Jinja2Template(body_text).render(**ctx)
        except Exception:
            pass
        for ph, val in _placeholders.items():
            subject = subject.replace(ph, val)
            body_html = body_html.replace(ph, val)
            body_text = body_text.replace(ph, val)

        original = {"subject": subject, "body_html": body_html, "body_text": body_text}

        # AI personalization
        ai_result = personalize_email_for_contact(
            db=db, tenant_id=tid,
            subject=subject, body_html=body_html, body_text=body_text,
            contact=contact, lead=lead,
        )

        results.append({
            "contact_id": contact.contact_id,
            "contact_name": f"{contact.first_name or ''} {contact.last_name or ''}".strip(),
            "contact_company": contact.client_name or "",
            "original": original,
            "personalized": {
                "subject": ai_result.get("subject", subject),
                "body_html": ai_result.get("body_html", body_html),
                "body_text": ai_result.get("body_text", body_text),
            },
            "ai_used": ai_result.get("ai_used", False),
            "tokens_used": ai_result.get("tokens_used", 0),
            "ai_error": ai_result.get("ai_error"),
        })

    return {"results": results, "campaign_id": campaign.campaign_id, "step_index": data.step_index}


@router.post("/drafts/{draft_id}/spam-fix")
def apply_spam_fixes(
    draft_id: int,
    data: SpamFixRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Apply spam word replacements to a draft."""
    from app.services.email_preview_service import apply_spam_fix
    result = apply_spam_fix(draft_id, data.replacements, db, tenant_id or 1)
    if result.get("error"):
        raise HTTPException(400, result["error"])
    return result


@router.delete("/drafts/bulk")
def bulk_delete_drafts(
    data: BulkDeleteDraftsRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Permanently delete multiple drafts. Admin and Super Admin."""
    if not data.draft_ids:
        raise HTTPException(400, "No draft IDs provided")

    query = db.query(OutreachDraft).filter(OutreachDraft.draft_id.in_(data.draft_ids))
    if tenant_id is not None:
        query = query.filter(OutreachDraft.tenant_id == tenant_id)
    deleted_count = query.delete(synchronize_session=False)
    db.commit()

    return {
        "message": f"Successfully deleted {deleted_count} draft(s)",
        "deleted_count": deleted_count,
    }


@router.delete("/drafts/all")
def delete_all_drafts(
    status: Optional[str] = Query(None, description="Only delete drafts with this status"),
    db: Session = Depends(get_db),
    user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Delete ALL drafts for the current tenant. Admin and Super Admin. Optionally filter by status."""
    query = db.query(OutreachDraft)
    if tenant_id is not None:
        query = query.filter(OutreachDraft.tenant_id == tenant_id)
    if status:
        query = query.filter(OutreachDraft.status == status)
    deleted_count = query.delete(synchronize_session=False)
    db.commit()
    return {
        "message": f"Successfully deleted {deleted_count} draft(s)",
        "deleted_count": deleted_count,
    }


# ─── Helpers ───────────────────────────────────────────────────────

def _draft_to_dict(draft: OutreachDraft, db: Session, include_details: bool = False) -> dict:
    """Convert draft to dict for API response."""
    d = {
        "draft_id": draft.draft_id,
        "tenant_id": draft.tenant_id,
        "contact_id": draft.contact_id,
        "lead_id": draft.lead_id,
        "campaign_id": draft.campaign_id,
        "step_id": draft.step_id,
        "mailbox_id": draft.mailbox_id,
        "subject": draft.subject,
        "body_html": draft.body_html,
        "body_text": draft.body_text,
        "original_subject": draft.original_subject,
        "original_body_html": draft.original_body_html,
        "status": draft.status.value if draft.status else "pending",
        "source": draft.source.value if draft.source else None,
        "spam_score": draft.spam_score,
        "spam_grade": draft.spam_grade,
        "flagged_words": json.loads(draft.flagged_words_json) if draft.flagged_words_json else [],
        "deliverability_score": draft.deliverability_score,
        "ai_rewritten": draft.ai_rewritten,
        "approved_by": draft.approved_by,
        "approved_at": draft.approved_at.isoformat() if draft.approved_at else None,
        "rejected_by": draft.rejected_by,
        "rejected_at": draft.rejected_at.isoformat() if draft.rejected_at else None,
        "sent_at": draft.sent_at.isoformat() if draft.sent_at else None,
        "expires_at": draft.expires_at.isoformat() if draft.expires_at else None,
        "batch_id": draft.batch_id,
        "variant_index": draft.variant_index,
        "created_at": draft.created_at.isoformat() if draft.created_at else None,
        "updated_at": draft.updated_at.isoformat() if draft.updated_at else None,
    }

    # Always include basic contact info
    contact = db.query(ContactDetails).filter(
        ContactDetails.contact_id == draft.contact_id
    ).first()
    if contact:
        d["contact"] = {
            "contact_id": contact.contact_id,
            "first_name": contact.first_name,
            "last_name": contact.last_name,
            "email": contact.email,
            "title": contact.title,
            "client_name": contact.client_name,
        }
    else:
        d["contact"] = None

    # Always include mailbox info
    mailbox = db.query(SenderMailbox).filter(
        SenderMailbox.mailbox_id == draft.mailbox_id
    ).first()
    if mailbox:
        d["mailbox"] = {
            "mailbox_id": mailbox.mailbox_id,
            "email": mailbox.email,
            "display_name": mailbox.display_name,
        }
    else:
        d["mailbox"] = None

    if include_details and draft.lead_id:
        lead = db.query(LeadDetails).filter(
            LeadDetails.lead_id == draft.lead_id
        ).first()
        if lead:
            d["lead"] = {
                "lead_id": lead.lead_id,
                "job_title": lead.job_title,
                "client_name": lead.client_name,
                "state": lead.state,
            }

    return d
