"""Deliverability Intelligence API endpoints.

Wraps existing backend services (send_gate, rendering_checker, email_humanizer,
spintax, engagement_tracker, esp_feedback, spam_checker, send_time_optimizer,
domain_reputation, domain_throttle) into REST endpoints for frontend consumption.
"""
from typing import Optional, List
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import func as sa_func

from app.api.deps.database import get_db
from app.api.deps.auth import get_current_active_user, require_role, get_current_tenant_id
from app.db.query_helpers import tenant_filter
from app.db.models.user import User, UserRole
from app.db.models.sender_mailbox import SenderMailbox
from app.db.models.contact import ContactDetails
from app.db.models.lead import LeadDetails
from app.db.models.campaign import Campaign
from app.db.models.outreach import OutreachEvent

router = APIRouter(prefix="/deliverability", tags=["deliverability"])


# ─── Schemas ───────────────────────────────────────────────────────

class PreSendCheckRequest(BaseModel):
    contact_id: int
    lead_id: Optional[int] = None
    campaign_id: Optional[int] = None

class RenderingCheckRequest(BaseModel):
    body_html: str

class HumanizeRequest(BaseModel):
    subject: str
    body_html: str
    body_text: str = ""
    intensity: str = Field("medium", pattern="^(light|medium|heavy)$")

class SpintaxPreviewRequest(BaseModel):
    text: str
    count: int = Field(5, ge=1, le=20)
    campaign_id: Optional[int] = None

class SpamReduceRequest(BaseModel):
    subject: str
    body_html: str
    replacements: List[dict] = Field(..., description="List of {original, replacement}")


# ─── 1. Health Summary ────────────────────────────────────────────

@router.get("/health-summary")
async def get_health_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Aggregate deliverability health across all mailboxes."""
    mailboxes = tenant_filter(
        db.query(SenderMailbox), SenderMailbox, tenant_id
    ).filter(SenderMailbox.is_active == True).all()

    if not mailboxes:
        return {
            "avg_health_score": 0,
            "total_mailboxes": 0,
            "dns_issues_count": 0,
            "avg_bounce_rate": 0,
            "avg_complaint_rate": 0,
            "bounce_trend": "stable",
            "send_gate_blocks_today": 0,
        }

    total = len(mailboxes)
    health_scores = [getattr(m, 'health_score', 100) or 100 for m in mailboxes]
    avg_health = sum(health_scores) / total if total else 0

    # Bounce and complaint rates from mailbox stats
    bounce_rates = []
    complaint_rates = []
    dns_issues = 0
    for m in mailboxes:
        sent = getattr(m, 'daily_emails_sent', 0) or 0
        total_sent = max(sent, getattr(m, 'total_emails_sent', 0) or 0, 1)
        bounce_count = getattr(m, 'bounce_count', 0) or 0
        complaint_count = getattr(m, 'complaint_count', 0) or 0
        bounce_rates.append(bounce_count / total_sent * 100 if total_sent > 0 else 0)
        complaint_rates.append(complaint_count / total_sent * 100 if total_sent > 0 else 0)
        # DNS issues — check if SPF/DKIM/DMARC fields exist and are failing
        spf = getattr(m, 'spf_status', None)
        dkim = getattr(m, 'dkim_status', None)
        dmarc = getattr(m, 'dmarc_status', None)
        if spf and spf != 'pass':
            dns_issues += 1
        if dkim and dkim != 'pass':
            dns_issues += 1
        if dmarc and dmarc != 'pass':
            dns_issues += 1

    avg_bounce = sum(bounce_rates) / total if total else 0
    avg_complaint = sum(complaint_rates) / total if total else 0

    # Send gate blocks today — count OutreachEvents with status 'blocked' today
    from datetime import datetime, timedelta
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    try:
        from app.db.models.automation_event import AutomationEvent
        blocks_today = tenant_filter(
            db.query(sa_func.count(AutomationEvent.event_id)),
            AutomationEvent, tenant_id
        ).filter(
            AutomationEvent.event_type == 'send_gate_block',
            AutomationEvent.created_at >= today_start,
        ).scalar() or 0
    except Exception:
        blocks_today = 0

    # Simple bounce trend (compare this week vs last week bounce counts)
    bounce_trend = "stable"
    try:
        week_ago = today_start - timedelta(days=7)
        two_weeks_ago = today_start - timedelta(days=14)
        this_week_bounces = tenant_filter(
            db.query(sa_func.count(OutreachEvent.event_id)),
            OutreachEvent, tenant_id
        ).filter(
            OutreachEvent.event_type == 'bounced',
            OutreachEvent.event_timestamp >= week_ago,
        ).scalar() or 0
        last_week_bounces = tenant_filter(
            db.query(sa_func.count(OutreachEvent.event_id)),
            OutreachEvent, tenant_id
        ).filter(
            OutreachEvent.event_type == 'bounced',
            OutreachEvent.event_timestamp >= two_weeks_ago,
            OutreachEvent.event_timestamp < week_ago,
        ).scalar() or 0
        if this_week_bounces > last_week_bounces * 1.2:
            bounce_trend = "up"
        elif this_week_bounces < last_week_bounces * 0.8:
            bounce_trend = "down"
    except Exception:
        pass

    return {
        "avg_health_score": round(avg_health, 1),
        "total_mailboxes": total,
        "dns_issues_count": dns_issues,
        "avg_bounce_rate": round(avg_bounce, 2),
        "avg_complaint_rate": round(avg_complaint, 3),
        "bounce_trend": bounce_trend,
        "send_gate_blocks_today": blocks_today,
    }


# ─── 2. Mailbox Health Detail ─────────────────────────────────────

@router.get("/mailbox/{mailbox_id}/health")
async def get_mailbox_health(
    mailbox_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Detailed health metrics for a single mailbox."""
    mailbox = tenant_filter(
        db.query(SenderMailbox), SenderMailbox, tenant_id
    ).filter(SenderMailbox.mailbox_id == mailbox_id).first()
    if not mailbox:
        raise HTTPException(status_code=404, detail="Mailbox not found")

    # Engagement rates
    try:
        from app.services.engagement_tracker import get_mailbox_engagement_rates
        engagement = get_mailbox_engagement_rates(db, mailbox_id, tenant_id)
    except Exception:
        engagement = {"reply_rate": 0, "bounce_rate": 0, "sent_count": 0}

    # Complaint rate
    try:
        from app.services.esp_feedback import check_complaint_rate
        complaint_rate, is_healthy = check_complaint_rate(db, mailbox_id, tenant_id)
    except Exception:
        complaint_rate = 0
        is_healthy = True

    # ISP detection
    try:
        from app.warmup.domain_reputation import detect_isp, ISP_PROFILES
        email = getattr(mailbox, 'email', '') or ''
        isp = detect_isp(email)
        isp_name = ISP_PROFILES.get(isp, {}).get('name', isp.title())
    except Exception:
        isp = "other"
        isp_name = "Other"

    health_score = getattr(mailbox, 'health_score', 100) or 100
    total_sent = max(getattr(mailbox, 'total_emails_sent', 0) or 0, 1)
    bounce_count = getattr(mailbox, 'bounce_count', 0) or 0
    bounce_rate = bounce_count / total_sent * 100

    # Health grade
    if health_score >= 90:
        grade = "A"
    elif health_score >= 80:
        grade = "B"
    elif health_score >= 70:
        grade = "C"
    elif health_score >= 60:
        grade = "D"
    else:
        grade = "F"

    return {
        "health_score": round(health_score, 1),
        "health_grade": grade,
        "bounce_rate_pct": round(bounce_rate, 2),
        "reply_rate_pct": round(engagement.get("reply_rate", 0) * 100, 2),
        "complaint_rate_pct": round(complaint_rate * 100, 3),
        "engagement_rate": round(engagement.get("reply_rate", 0), 4),
        "is_healthy": is_healthy,
        "isp": isp,
        "isp_name": isp_name,
    }


# ─── 3. Pre-Send Check ────────────────────────────────────────────

@router.post("/pre-send-check")
async def pre_send_check(
    request: PreSendCheckRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Run the send gate in dry-run mode to check if an email can be sent."""
    contact = tenant_filter(
        db.query(ContactDetails), ContactDetails, tenant_id
    ).filter(ContactDetails.contact_id == request.contact_id).first()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    lead = None
    if request.lead_id:
        lead = tenant_filter(
            db.query(LeadDetails), LeadDetails, tenant_id
        ).filter(LeadDetails.lead_id == request.lead_id).first()

    campaign = None
    if request.campaign_id:
        campaign = tenant_filter(
            db.query(Campaign), Campaign, tenant_id
        ).filter(Campaign.campaign_id == request.campaign_id).first()

    try:
        from app.services.send_gate import unified_send_gate
        result = unified_send_gate(
            db=db,
            contact=contact,
            tenant_id=tenant_id,
            lead=lead,
            campaign=campaign,
            dry_run=True,
        )
        return {
            "allowed": result.allowed,
            "reason_code": result.reason_code,
            "reason_message": result.reason_message,
            "checks": [
                {"name": c.name, "passed": c.passed, "reason": c.reason}
                for c in result.checks
            ],
        }
    except Exception as e:
        return {
            "allowed": False,
            "reason_code": "ERROR",
            "reason_message": str(e),
            "checks": [],
        }


# ─── 4. Rendering Check ───────────────────────────────────────────

@router.post("/rendering-check")
async def rendering_check(
    request: RenderingCheckRequest,
    current_user: User = Depends(get_current_active_user),
):
    """Check email HTML for rendering issues across email clients."""
    try:
        from app.services.rendering_checker import check_rendering
        result = check_rendering(request.body_html)
        return result
    except Exception as e:
        return {"warnings": [], "stats": {}, "score": 100, "error": str(e)}


# ─── 5. Humanize Email ────────────────────────────────────────────

@router.post("/humanize")
async def humanize_email(
    request: HumanizeRequest,
    current_user: User = Depends(get_current_active_user),
):
    """Humanize email content to avoid AI detection."""
    try:
        from app.services.email_humanizer import humanize_email as do_humanize, compute_burstiness_score
        # Before score
        plain_before = request.body_text or request.body_html
        burstiness_before = compute_burstiness_score(plain_before)

        result = do_humanize(
            subject=request.subject,
            body_html=request.body_html,
            body_text=request.body_text,
            intensity=request.intensity,
        )

        # After score
        plain_after = result.get("body_text", "") or result.get("body_html", "")
        burstiness_after = compute_burstiness_score(plain_after)

        return {
            **result,
            "burstiness_before": round(burstiness_before, 3),
            "burstiness_after": round(burstiness_after, 3),
        }
    except Exception as e:
        return {
            "subject": request.subject,
            "body_html": request.body_html,
            "body_text": request.body_text,
            "modifications": [],
            "burstiness_before": 0,
            "burstiness_after": 0,
            "error": str(e),
        }


# ─── 6. Send Time Optimizer ───────────────────────────────────────

@router.get("/send-times")
async def get_optimal_send_times(
    state: Optional[str] = Query(None, description="US state code (e.g., TX, CA)"),
    preferred_hour: Optional[int] = Query(None, ge=0, le=23),
    current_user: User = Depends(get_current_active_user),
):
    """Calculate optimal send time for a recipient's timezone."""
    try:
        from app.services.send_time_optimizer import calculate_optimal_send_time
        result = calculate_optimal_send_time(
            state=state,
            preferred_hour=preferred_hour,
        )
        # Serialize datetime to ISO string
        result["send_at_utc"] = result["send_at_utc"].isoformat() if result.get("send_at_utc") else None
        return result
    except Exception as e:
        return {
            "send_at_utc": None,
            "recipient_local_time": None,
            "timezone": "America/New_York",
            "combined_score": 0,
            "error": str(e),
        }


# ─── 7. Contact Engagement Score ──────────────────────────────────

@router.get("/engagement/{contact_id}")
async def get_engagement_score(
    contact_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Get engagement score and tier for a contact."""
    contact = tenant_filter(
        db.query(ContactDetails), ContactDetails, tenant_id
    ).filter(ContactDetails.contact_id == contact_id).first()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    try:
        from app.services.engagement_tracker import calculate_engagement_score
        result = calculate_engagement_score(db, contact_id, tenant_id)
        # Serialize datetime
        if result.get("last_engagement_at"):
            result["last_engagement_at"] = result["last_engagement_at"].isoformat()
        return result
    except Exception as e:
        return {
            "score": 0,
            "tier": "dead",
            "signals": {},
            "total_sent": 0,
            "last_engagement_at": None,
            "error": str(e),
        }


# ─── 8. Spintax Preview ───────────────────────────────────────────

@router.post("/spintax-preview")
async def spintax_preview(
    request: SpintaxPreviewRequest,
    current_user: User = Depends(get_current_active_user),
):
    """Preview multiple spintax variations of email content."""
    try:
        from app.services.spintax import process_spintax, count_variants, validate_spintax

        errors = validate_spintax(request.text)
        total = count_variants(request.text)

        variants = []
        for i in range(request.count):
            seed = (request.campaign_id or 0) * 1000 + i + 1
            variant = process_spintax(request.text, seed=seed, campaign_id=request.campaign_id)
            variants.append(variant)

        return {
            "variants": variants,
            "total_variants": total,
            "errors": errors,
        }
    except Exception as e:
        return {
            "variants": [request.text],
            "total_variants": 1,
            "errors": [str(e)],
        }


# ─── 9. ISP Profiles ──────────────────────────────────────────────

@router.get("/isp-profiles")
async def get_isp_profiles(
    current_user: User = Depends(get_current_active_user),
):
    """Get ISP warmup profiles and strategies."""
    try:
        from app.warmup.domain_reputation import ISP_PROFILES
        # Return safe subset (no internal implementation details)
        profiles = {}
        for isp_key, profile in ISP_PROFILES.items():
            profiles[isp_key] = {
                "name": profile.get("name", isp_key.title()),
                "domains": profile.get("domains", []),
                "strategy": profile.get("strategy", ""),
                "description": profile.get("description", ""),
                "recommended_daily_ramp": profile.get("recommended_daily_ramp", []),
                "recommended_reply_rate": profile.get("recommended_reply_rate", 0),
                "key_factors": profile.get("key_factors", []),
            }
        return {"profiles": profiles}
    except Exception as e:
        return {"profiles": {}, "error": str(e)}


# ─── 10. Complaint Stats ──────────────────────────────────────────

@router.get("/complaint-stats")
async def get_complaint_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Get per-mailbox complaint rate statistics."""
    try:
        from app.services.esp_feedback import get_complaint_stats as fetch_stats
        stats = fetch_stats(db, tenant_id)
        return {"stats": stats}
    except Exception as e:
        return {"stats": [], "error": str(e)}


# ─── 11. Spam Reduce ──────────────────────────────────────────────

@router.post("/spam-reduce")
async def spam_reduce(
    request: SpamReduceRequest,
    current_user: User = Depends(get_current_active_user),
):
    """Apply spam-word replacements and return before/after scores."""
    try:
        from app.services.spam_checker import check_spam_score

        # Before scores
        before = check_spam_score(request.subject, request.body_html)

        # Apply replacements
        from app.services.spam_checker import html_safe_replace

        new_subject = request.subject
        new_body = request.body_html
        for rep in request.replacements:
            original = rep.get("original", "")
            replacement = rep.get("replacement", "")
            if original:
                new_subject = new_subject.replace(original, replacement)
                new_body = html_safe_replace(new_body, original, replacement)

        # After scores
        after = check_spam_score(new_subject, new_body)

        return {
            "before_score": before["score"],
            "before_grade": before["grade"],
            "after_score": after["score"],
            "after_grade": after["grade"],
            "delta": before["score"] - after["score"],
            "new_subject": new_subject,
            "new_body_html": new_body,
        }
    except Exception as e:
        return {
            "before_score": 0,
            "before_grade": "clean",
            "after_score": 0,
            "after_grade": "clean",
            "delta": 0,
            "new_subject": request.subject,
            "new_body_html": request.body_html,
            "error": str(e),
        }


# ─── 12. Humanize Preview (preview-only, no apply) ────────────────

@router.post("/humanize-preview")
async def humanize_preview(
    request: HumanizeRequest,
    current_user: User = Depends(get_current_active_user),
):
    """Preview humanization without applying to any draft."""
    # Same logic as /humanize — both are stateless
    return await humanize_email(request, current_user)


# ─── Seed Test / Inbox Placement ─────────────────────────────────

@router.post("/seed-test/{mailbox_id}")
def run_seed_test_endpoint(
    mailbox_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Send test emails to seed accounts for inbox placement testing."""
    from app.services.seed_tester import run_seed_test

    mailbox = tenant_filter(db.query(SenderMailbox), tenant_id).filter(
        SenderMailbox.mailbox_id == mailbox_id
    ).first()
    if not mailbox:
        raise HTTPException(status_code=404, detail="Mailbox not found")
    return run_seed_test(mailbox_id, db)


@router.post("/seed-test/{test_run_id}/check")
def check_seed_results_endpoint(
    test_run_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN])),
):
    """Poll IMAP accounts to check inbox placement for a seed test run."""
    from app.services.seed_tester import check_seed_results
    return check_seed_results(test_run_id, db)


@router.get("/seed-test/{test_run_id}/results")
def get_seed_test_results(
    test_run_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN])),
):
    """Get results for a specific seed test run."""
    from app.services.seed_tester import get_test_results
    return get_test_results(test_run_id, db)
