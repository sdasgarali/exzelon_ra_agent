"""Warmup Engine API endpoints - Enterprise Edition."""
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc
from datetime import datetime, timedelta
import json
import io

from app.api.deps import get_db, require_role, get_current_tenant_id
from app.db.models.user import User, UserRole
from app.db.models.sender_mailbox import SenderMailbox, WarmupStatus
from app.db.models.warmup_email import WarmupEmail
from app.db.models.warmup_daily_log import WarmupDailyLog
from app.db.models.warmup_alert import WarmupAlert, AlertType, AlertSeverity
from app.db.models.warmup_profile import WarmupProfile
from app.db.models.dns_check_result import DNSCheckResult
from app.db.models.blacklist_check_result import BlacklistCheckResult

from app.schemas.warmup import (
    WarmupConfig, WarmupConfigUpdate, WarmupStatusResponse,
    MailboxWarmupStatus, WarmupAssessmentResult,
    WarmupScheduleResponse, HealthScoresResponse, MailboxHealthScore,
    WarmupEmailListResponse, WarmupEmailSchema, WarmupEmailDetailSchema,
    WarmupAnalyticsResponse, WarmupDailyLogSchema,
    WarmupAlertSchema, WarmupAlertListResponse,
    WarmupProfileSchema, WarmupProfileCreate, WarmupProfileUpdate, WarmupProfileListResponse,
    DNSCheckResultSchema, DNSHealthResponse,
    BlacklistCheckResultSchema, BlacklistCheckResponse,
)

from app.services.pipelines.warmup_engine import (
    load_warmup_config, calculate_health_score, get_warmup_phase,
    run_warmup_assessment, build_warmup_schedule,
)
from app.services.warmup.peer_warmup import run_peer_warmup_cycle, run_auto_reply_cycle
from app.services.warmup.dns_checker import run_dns_health_check
from app.services.warmup.blacklist_monitor import run_blacklist_check as run_bl_check
from app.services.warmup.inbox_placement import run_placement_test
from app.services.warmup.auto_recovery import start_recovery
from app.services.warmup.report_exporter import export_csv, export_json
from app.services.warmup.scheduler import get_scheduler_status

router = APIRouter(prefix="/warmup", tags=["Warmup Engine"])


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _build_mailbox_warmup_status(mb: SenderMailbox, config: dict) -> MailboxWarmupStatus:
    """Build warmup status detail for a single mailbox."""
    health = calculate_health_score(mb, config)
    day = mb.warmup_days_completed or 0
    phase = 0
    phase_name = ""
    if day > 0:
        phase, phase_name = get_warmup_phase(day, config)
    elif mb.warmup_status in (WarmupStatus.WARMING_UP, WarmupStatus.RECOVERING):
        phase = 1
        phase_name = "Initial"

    total_sent = mb.total_emails_sent or 0
    bounce_rate = (mb.bounce_count / total_sent * 100) if total_sent > 0 else 0.0
    reply_rate = (mb.reply_count / total_sent * 100) if total_sent > 0 else 0.0
    complaint_rate = (mb.complaint_count / total_sent * 100) if total_sent > 0 else 0.0

    return MailboxWarmupStatus(
        mailbox_id=mb.mailbox_id,
        email=mb.email,
        display_name=mb.display_name,
        warmup_status=mb.warmup_status.value,
        is_active=mb.is_active,
        warmup_day=day,
        warmup_phase=phase,
        phase_name=phase_name,
        health_score=health["health_score"],
        daily_limit=mb.daily_send_limit,
        emails_sent_today=mb.emails_sent_today,
        total_emails_sent=total_sent,
        bounce_rate=round(bounce_rate, 2),
        reply_rate=round(reply_rate, 2),
        complaint_rate=round(complaint_rate, 3),
        warmup_started_at=mb.warmup_started_at,
        warmup_completed_at=mb.warmup_completed_at,
        connection_status=mb.connection_status or "untested",
        dns_score=mb.dns_score or 0,
        is_blacklisted=mb.is_blacklisted or False,
        warmup_profile_id=mb.warmup_profile_id,
    )


# ---------------------------------------------------------------------------
# 1. GET /status
# ---------------------------------------------------------------------------

@router.get("/status", response_model=WarmupStatusResponse)
async def get_warmup_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Get all mailbox warmup statuses + aggregate stats.

    Returns all mailboxes with their warmup status and enterprise metrics.
    """
    config = load_warmup_config(db)
    q = db.query(SenderMailbox).filter(SenderMailbox.connection_status == "successful")
    if tenant_id is not None:
        q = q.filter(SenderMailbox.tenant_id == tenant_id)
    mailboxes = q.order_by(SenderMailbox.email).all()

    statuses = [_build_mailbox_warmup_status(mb, config) for mb in mailboxes]

    warming_up = sum(1 for s in statuses if s.warmup_status == "warming_up")
    cold_ready = sum(1 for s in statuses if s.warmup_status == "cold_ready")
    active = sum(1 for s in statuses if s.warmup_status == "active")
    paused = sum(1 for s in statuses if s.warmup_status == "paused")
    recovering_count = sum(1 for s in statuses if s.warmup_status == "recovering")
    dns_issues_count = sum(1 for mb in mailboxes if (mb.dns_score or 0) < 70)

    scores = [s.health_score for s in statuses if s.health_score > 0]
    avg_health = sum(scores) / len(scores) if scores else 0.0

    return WarmupStatusResponse(
        mailboxes=statuses,
        total_mailboxes=len(statuses),
        warming_up_count=warming_up,
        cold_ready_count=cold_ready,
        active_count=active,
        paused_count=paused,
        recovering_count=recovering_count,
        avg_health_score=round(avg_health, 1),
        dns_issues_count=dns_issues_count,
    )


# ---------------------------------------------------------------------------
# 2. GET /config
# ---------------------------------------------------------------------------

@router.get("/config")
async def get_warmup_config(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR])),
):
    """Get current warmup configuration."""
    config = load_warmup_config(db)
    return {
        "phase_1": {
            "days": config["phase_1_days"],
            "min_emails": config["phase_1_min_emails"],
            "max_emails": config["phase_1_max_emails"],
        },
        "phase_2": {
            "days": config["phase_2_days"],
            "min_emails": config["phase_2_min_emails"],
            "max_emails": config["phase_2_max_emails"],
        },
        "phase_3": {
            "days": config["phase_3_days"],
            "min_emails": config["phase_3_min_emails"],
            "max_emails": config["phase_3_max_emails"],
        },
        "phase_4": {
            "days": config["phase_4_days"],
            "min_emails": config["phase_4_min_emails"],
            "max_emails": config["phase_4_max_emails"],
        },
        "bounce_rate_good": config["bounce_rate_good"],
        "bounce_rate_bad": config["bounce_rate_bad"],
        "reply_rate_good": config["reply_rate_good"],
        "complaint_rate_bad": config["complaint_rate_bad"],
        "weight_bounce_rate": config["weight_bounce_rate"],
        "weight_reply_rate": config["weight_reply_rate"],
        "weight_complaint_rate": config["weight_complaint_rate"],
        "weight_age": config["weight_age"],
        "auto_pause_bounce_rate": config["auto_pause_bounce_rate"],
        "auto_pause_complaint_rate": config["auto_pause_complaint_rate"],
        "min_emails_for_scoring": config["min_emails_for_scoring"],
        "active_health_threshold": config["active_health_threshold"],
        "active_min_days": config["active_min_days"],
        "total_days": config["total_days"],
    }


# ---------------------------------------------------------------------------
# 3. PUT /config
# ---------------------------------------------------------------------------

@router.put("/config")
async def update_warmup_config(
    config_update: WarmupConfigUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
):
    """Update warmup configuration (Admin only)."""
    from app.db.models.settings import Settings

    updates = config_update.model_dump(exclude_unset=True)
    updated_keys: List[str] = []

    field_map = {
        "bounce_rate_good": "warmup_bounce_rate_good",
        "bounce_rate_bad": "warmup_bounce_rate_bad",
        "reply_rate_good": "warmup_reply_rate_good",
        "complaint_rate_bad": "warmup_complaint_rate_bad",
        "weight_bounce_rate": "warmup_weight_bounce_rate",
        "weight_reply_rate": "warmup_weight_reply_rate",
        "weight_complaint_rate": "warmup_weight_complaint_rate",
        "weight_age": "warmup_weight_age",
        "auto_pause_bounce_rate": "warmup_auto_pause_bounce_rate",
        "auto_pause_complaint_rate": "warmup_auto_pause_complaint_rate",
        "min_emails_for_scoring": "warmup_min_emails_for_scoring",
        "active_health_threshold": "warmup_active_health_threshold",
        "active_min_days": "warmup_active_min_days",
        "total_days": "warmup_total_days",
        "daily_increment": "warmup_daily_increment",
    }

    for field, value in updates.items():
        if field.startswith("phase_") and isinstance(value, dict):
            phase_num = field.split("_")[1]
            for sub_key, sub_val in value.items():
                setting_key = f"warmup_phase_{phase_num}_{sub_key}"
                setting = db.query(Settings).filter(Settings.key == setting_key).first()
                if setting:
                    setting.value_json = json.dumps(sub_val)
                    setting.updated_by = current_user.email
                    updated_keys.append(setting_key)
        elif field in field_map:
            setting_key = field_map[field]
            setting = db.query(Settings).filter(Settings.key == setting_key).first()
            if setting:
                setting.value_json = json.dumps(value)
                setting.updated_by = current_user.email
                updated_keys.append(setting_key)

    db.commit()
    return {"message": f"Updated {len(updated_keys)} settings", "updated_keys": updated_keys}


# ---------------------------------------------------------------------------
# 4. POST /assess
# ---------------------------------------------------------------------------

@router.post("/assess", response_model=WarmupAssessmentResult)
async def assess_all_mailboxes(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR])),
):
    """Assess all active mailboxes."""
    result = run_warmup_assessment(triggered_by=current_user.email)
    return WarmupAssessmentResult(**result)


# ---------------------------------------------------------------------------
# 5. POST /assess/{mailbox_id}
# ---------------------------------------------------------------------------

@router.post("/assess/{mailbox_id}", response_model=WarmupAssessmentResult)
async def assess_single_mailbox(
    mailbox_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR])),
):
    """Assess a single mailbox (synchronous)."""
    mailbox = db.query(SenderMailbox).filter(SenderMailbox.mailbox_id == mailbox_id).first()
    if not mailbox:
        raise HTTPException(status_code=404, detail="Mailbox not found")

    result = run_warmup_assessment(triggered_by=current_user.email, mailbox_id=mailbox_id)
    return WarmupAssessmentResult(**result)


# ---------------------------------------------------------------------------
# 6. GET /schedule
# ---------------------------------------------------------------------------

@router.get("/schedule", response_model=WarmupScheduleResponse)
async def get_warmup_schedule(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR])),
):
    """Get day-by-day warmup schedule."""
    config = load_warmup_config(db)
    schedule = build_warmup_schedule(config)
    return WarmupScheduleResponse(**schedule)


# ---------------------------------------------------------------------------
# 7. GET /health-scores
# ---------------------------------------------------------------------------

@router.get("/health-scores", response_model=HealthScoresResponse)
async def get_health_scores(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Get health scores for all mailboxes."""
    config = load_warmup_config(db)
    q = db.query(SenderMailbox).filter(
        SenderMailbox.connection_status == "successful"
    )
    if tenant_id is not None:
        q = q.filter(SenderMailbox.tenant_id == tenant_id)
    mailboxes = q.order_by(SenderMailbox.email).all()

    scores: List[MailboxHealthScore] = []
    for mb in mailboxes:
        health = calculate_health_score(mb, config)
        scores.append(MailboxHealthScore(
            mailbox_id=mb.mailbox_id,
            email=mb.email,
            health_score=health["health_score"],
            bounce_score=health["bounce_score"],
            reply_score=health["reply_score"],
            complaint_score=health["complaint_score"],
            age_score=health["age_score"],
            bounce_rate=health["bounce_rate"],
            reply_rate=health["reply_rate"],
            complaint_rate=health["complaint_rate"],
            account_age_days=health["account_age_days"],
        ))

    avg = sum(s.health_score for s in scores) / len(scores) if scores else 0.0

    return HealthScoresResponse(
        mailboxes=scores,
        avg_health_score=round(avg, 1),
    )


# ---------------------------------------------------------------------------
# 8. POST /peer/send
# ---------------------------------------------------------------------------

@router.post("/peer/send")
async def trigger_peer_warmup(
    mailbox_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
):
    """Trigger a peer-to-peer warmup cycle.

    If mailbox_id is provided, only that mailbox participates.
    Otherwise all eligible mailboxes are included.
    """
    result = run_peer_warmup_cycle(db, mailbox_id=mailbox_id)
    return {
        "message": "Peer warmup cycle completed",
        "result": result,
    }


# ---------------------------------------------------------------------------
# 8b. POST /peer/auto-reply
# ---------------------------------------------------------------------------

@router.post("/peer/auto-reply")
async def trigger_auto_reply(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
):
    """Trigger an auto-reply cycle manually.

    Finds warmup emails that were sent but never replied to,
    and generates natural-looking replies to boost reply rates.
    """
    result = run_auto_reply_cycle(db)
    return {
        "message": "Auto-reply cycle completed",
        "result": result,
    }


# ---------------------------------------------------------------------------
# 9. GET /peer/history
# ---------------------------------------------------------------------------

@router.get("/peer/history", response_model=WarmupEmailListResponse)
async def get_peer_history(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    mailbox_id: Optional[int] = None,
    direction: Optional[str] = Query(None, pattern="^(sent|received|all)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR])),
):
    """Get paginated peer warmup email history, optionally filtered by mailbox and direction."""
    query = db.query(WarmupEmail).order_by(desc(WarmupEmail.sent_at))

    if mailbox_id is not None:
        if direction == "sent":
            query = query.filter(WarmupEmail.sender_mailbox_id == mailbox_id)
        elif direction == "received":
            query = query.filter(WarmupEmail.receiver_mailbox_id == mailbox_id)
        else:
            query = query.filter(
                (WarmupEmail.sender_mailbox_id == mailbox_id)
                | (WarmupEmail.receiver_mailbox_id == mailbox_id)
            )

    total = query.count()
    items = query.offset((page - 1) * limit).limit(limit).all()

    return WarmupEmailListResponse(
        items=[WarmupEmailSchema.model_validate(e) for e in items],
        total=total,
        page=page,
        limit=limit,
    )


# ---------------------------------------------------------------------------
# 9b. GET /peer/history/{email_id} - Single warmup email detail
# ---------------------------------------------------------------------------

@router.get("/peer/history/{email_id}", response_model=WarmupEmailDetailSchema)
async def get_peer_email_detail(
    email_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR])),
):
    """Get full detail of a single warmup email including body content."""
    email_record = db.query(WarmupEmail).filter(WarmupEmail.id == email_id).first()
    if not email_record:
        raise HTTPException(status_code=404, detail="Warmup email not found")

    # Resolve sender/receiver emails
    sender_mb = db.query(SenderMailbox).filter(SenderMailbox.mailbox_id == email_record.sender_mailbox_id).first()
    receiver_mb = db.query(SenderMailbox).filter(SenderMailbox.mailbox_id == email_record.receiver_mailbox_id).first() if email_record.receiver_mailbox_id else None

    data = WarmupEmailDetailSchema.model_validate(email_record)
    data.sender_email = sender_mb.email if sender_mb else None
    data.receiver_email = receiver_mb.email if receiver_mb else None
    return data


# ---------------------------------------------------------------------------
# 10. GET /analytics
# ---------------------------------------------------------------------------

@router.get("/analytics", response_model=WarmupAnalyticsResponse)
async def get_analytics(
    days: int = Query(30, ge=1, le=365),
    mailbox_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR])),
):
    """Get time-series warmup analytics data."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    query = db.query(WarmupDailyLog).filter(WarmupDailyLog.log_date >= cutoff.date())

    if mailbox_id is not None:
        query = query.filter(WarmupDailyLog.mailbox_id == mailbox_id)

    logs = query.order_by(WarmupDailyLog.log_date).all()

    total_sent = sum(log.emails_sent for log in logs)
    total_received = sum(log.emails_received for log in logs)
    total_opens = sum(log.opens for log in logs)
    total_replies = sum(log.replies for log in logs)
    total_bounces = sum(log.bounces for log in logs)
    avg_health = (sum(log.health_score for log in logs) / len(logs)) if logs else 0.0

    return WarmupAnalyticsResponse(
        mailbox_id=mailbox_id,
        days=days,
        daily_logs=[WarmupDailyLogSchema.model_validate(log) for log in logs],
        summary={
            "total_sent": total_sent,
            "total_received": total_received,
            "total_opens": total_opens,
            "total_replies": total_replies,
            "total_bounces": total_bounces,
            "avg_health_score": round(avg_health, 1),
            "log_count": len(logs),
        },
    )


# ---------------------------------------------------------------------------
# 11. POST /dns-check
# ---------------------------------------------------------------------------

@router.post("/dns-check")
async def run_dns_check(
    mailbox_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Run DNS health check for one or all mailboxes."""
    if mailbox_id is not None:
        mailbox = db.query(SenderMailbox).filter(SenderMailbox.mailbox_id == mailbox_id).first()
        if not mailbox:
            raise HTTPException(status_code=404, detail="Mailbox not found")
        result = run_dns_health_check(mailbox_id, db)
        return {"message": "DNS check completed", "mailbox_id": mailbox_id, "result": result}

    # Check all active mailboxes
    q = db.query(SenderMailbox).filter(
        SenderMailbox.is_active == True,
        SenderMailbox.connection_status == "successful",
    )
    if tenant_id is not None:
        q = q.filter(SenderMailbox.tenant_id == tenant_id)
    mailboxes = q.all()
    results = []
    for mb in mailboxes:
        try:
            r = run_dns_health_check(mb.mailbox_id, db)
            results.append(r)
        except Exception as e:
            results.append({"mailbox_id": mb.mailbox_id, "error": str(e)})
    return {"message": f"DNS check completed for {len(results)} mailboxes", "results": results}


# ---------------------------------------------------------------------------
# 12. GET /dns/{mailbox_id}
# ---------------------------------------------------------------------------

@router.get("/dns/{mailbox_id}", response_model=DNSHealthResponse)
async def get_dns_results(
    mailbox_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR])),
):
    """Get latest DNS check result for a mailbox."""
    mailbox = db.query(SenderMailbox).filter(SenderMailbox.mailbox_id == mailbox_id).first()
    if not mailbox:
        raise HTTPException(status_code=404, detail="Mailbox not found")

    result = (
        db.query(DNSCheckResult)
        .filter(DNSCheckResult.mailbox_id == mailbox_id)
        .order_by(desc(DNSCheckResult.checked_at))
        .first()
    )

    domain = mailbox.email.split("@")[1] if "@" in mailbox.email else mailbox.email

    return DNSHealthResponse(
        mailbox_id=mailbox_id,
        domain=domain,
        results=DNSCheckResultSchema.model_validate(result) if result else None,
        score=result.overall_score if result else 0,
    )


# ---------------------------------------------------------------------------
# 13. POST /blacklist-check
# ---------------------------------------------------------------------------

@router.post("/blacklist-check")
async def run_blacklist_check_endpoint(
    mailbox_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Run blacklist check for one or all mailboxes."""
    if mailbox_id is not None:
        mailbox = db.query(SenderMailbox).filter(SenderMailbox.mailbox_id == mailbox_id).first()
        if not mailbox:
            raise HTTPException(status_code=404, detail="Mailbox not found")
        result = run_bl_check(mailbox_id, db)
        return {"message": "Blacklist check completed", "mailbox_id": mailbox_id, "result": result}

    # Check all active mailboxes
    q = db.query(SenderMailbox).filter(
        SenderMailbox.is_active == True,
        SenderMailbox.connection_status == "successful",
    )
    if tenant_id is not None:
        q = q.filter(SenderMailbox.tenant_id == tenant_id)
    mailboxes = q.all()
    results = []
    for mb in mailboxes:
        try:
            r = run_bl_check(mb.mailbox_id, db)
            results.append(r)
        except Exception as e:
            results.append({"mailbox_id": mb.mailbox_id, "error": str(e)})
    return {"message": f"Blacklist check completed for {len(results)} mailboxes", "results": results}


# ---------------------------------------------------------------------------
# 14. GET /blacklist/{mailbox_id}
# ---------------------------------------------------------------------------

@router.get("/blacklist/{mailbox_id}", response_model=BlacklistCheckResponse)
async def get_blacklist_results(
    mailbox_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR])),
):
    """Get latest blacklist check result for a mailbox."""
    mailbox = db.query(SenderMailbox).filter(SenderMailbox.mailbox_id == mailbox_id).first()
    if not mailbox:
        raise HTTPException(status_code=404, detail="Mailbox not found")

    result = (
        db.query(BlacklistCheckResult)
        .filter(BlacklistCheckResult.mailbox_id == mailbox_id)
        .order_by(desc(BlacklistCheckResult.checked_at))
        .first()
    )

    domain = mailbox.email.split("@")[1] if "@" in mailbox.email else mailbox.email

    return BlacklistCheckResponse(
        mailbox_id=mailbox_id,
        domain=domain,
        results=BlacklistCheckResultSchema.model_validate(result) if result else None,
        is_clean=result.is_clean if result else True,
    )


# ---------------------------------------------------------------------------
# 15. POST /placement-test/{mailbox_id}
# ---------------------------------------------------------------------------

@router.post("/placement-test/{mailbox_id}")
async def run_placement_test_endpoint(
    mailbox_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
):
    """Run inbox placement test for a specific mailbox."""
    mailbox = db.query(SenderMailbox).filter(SenderMailbox.mailbox_id == mailbox_id).first()
    if not mailbox:
        raise HTTPException(status_code=404, detail="Mailbox not found")

    result = run_placement_test(mailbox_id, db)
    return {"message": "Placement test completed", "mailbox_id": mailbox_id, "result": result}


# ---------------------------------------------------------------------------
# 16. GET /alerts
# ---------------------------------------------------------------------------

@router.get("/alerts", response_model=WarmupAlertListResponse)
async def get_alerts(
    severity: Optional[str] = None,
    is_read: Optional[bool] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR])),
):
    """Get paginated warmup alerts with optional filters."""
    query = db.query(WarmupAlert)

    if severity is not None:
        query = query.filter(WarmupAlert.severity == severity)
    if is_read is not None:
        query = query.filter(WarmupAlert.is_read == is_read)

    total = query.count()
    unread_count = db.query(WarmupAlert).filter(WarmupAlert.is_read == False).count()

    items = (
        query.order_by(desc(WarmupAlert.created_at))
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )

    return WarmupAlertListResponse(
        items=[WarmupAlertSchema.model_validate(a) for a in items],
        total=total,
        unread_count=unread_count,
    )


# ---------------------------------------------------------------------------
# 17. PUT /alerts/{alert_id}/read
# ---------------------------------------------------------------------------

@router.put("/alerts/{alert_id}/read")
async def mark_alert_read(
    alert_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR])),
):
    """Mark a single alert as read."""
    alert = db.query(WarmupAlert).filter(WarmupAlert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    alert.is_read = True
    db.commit()
    return {"message": "Alert marked as read", "alert_id": alert_id}


# ---------------------------------------------------------------------------
# 18. PUT /alerts/read-all
# ---------------------------------------------------------------------------

@router.put("/alerts/read-all")
async def mark_all_alerts_read(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR])),
):
    """Mark all unread alerts as read."""
    count = (
        db.query(WarmupAlert)
        .filter(WarmupAlert.is_read == False)
        .update({"is_read": True})
    )
    db.commit()
    return {"message": f"Marked {count} alerts as read", "updated": count}


# ---------------------------------------------------------------------------
# 19. GET /alerts/unread-count
# ---------------------------------------------------------------------------

@router.get("/alerts/unread-count")
async def get_unread_alert_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR])),
):
    """Get the count of unread alerts."""
    count = db.query(WarmupAlert).filter(WarmupAlert.is_read == False).count()
    return {"unread_count": count}


# ---------------------------------------------------------------------------
# 20. GET /profiles
# ---------------------------------------------------------------------------

@router.get("/profiles", response_model=WarmupProfileListResponse)
async def list_profiles(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR])),
):
    """List all warmup profiles."""
    profiles = db.query(WarmupProfile).order_by(WarmupProfile.name).all()
    return WarmupProfileListResponse(
        items=[WarmupProfileSchema.model_validate(p) for p in profiles],
        total=len(profiles),
    )


# ---------------------------------------------------------------------------
# 21. POST /profiles
# ---------------------------------------------------------------------------

@router.post("/profiles", response_model=WarmupProfileSchema, status_code=201)
async def create_profile(
    profile_in: WarmupProfileCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
):
    """Create a new warmup profile (Admin only)."""
    profile = WarmupProfile(
        name=profile_in.name,
        description=profile_in.description,
        config_json=profile_in.config_json,
        is_system=False,
        is_default=False,
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return WarmupProfileSchema.model_validate(profile)


# ---------------------------------------------------------------------------
# 22. PUT /profiles/{profile_id}
# ---------------------------------------------------------------------------

@router.put("/profiles/{profile_id}", response_model=WarmupProfileSchema)
async def update_profile(
    profile_id: int,
    profile_in: WarmupProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
):
    """Update a warmup profile (Admin only)."""
    profile = db.query(WarmupProfile).filter(WarmupProfile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    updates = profile_in.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(profile, field, value)

    db.commit()
    db.refresh(profile)
    return WarmupProfileSchema.model_validate(profile)


# ---------------------------------------------------------------------------
# 23. DELETE /profiles/{profile_id}
# ---------------------------------------------------------------------------

@router.delete("/profiles/{profile_id}")
async def delete_profile(
    profile_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
):
    """Delete a warmup profile (Admin only). System profiles cannot be deleted."""
    profile = db.query(WarmupProfile).filter(WarmupProfile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    if profile.is_system:
        raise HTTPException(status_code=400, detail="System profiles cannot be deleted")

    db.delete(profile)
    db.commit()
    return {"message": "Profile deleted", "profile_id": profile_id}


# ---------------------------------------------------------------------------
# 24. POST /profiles/{profile_id}/apply/{mailbox_id}
# ---------------------------------------------------------------------------

@router.post("/profiles/{profile_id}/apply/{mailbox_id}")
async def apply_profile(
    profile_id: int,
    mailbox_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
):
    """Apply a warmup profile to a specific mailbox (Admin only)."""
    profile = db.query(WarmupProfile).filter(WarmupProfile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    mailbox = db.query(SenderMailbox).filter(SenderMailbox.mailbox_id == mailbox_id).first()
    if not mailbox:
        raise HTTPException(status_code=404, detail="Mailbox not found")

    mailbox.warmup_profile_id = profile_id
    db.commit()
    return {
        "message": f"Profile '{profile.name}' applied to mailbox '{mailbox.email}'",
        "profile_id": profile_id,
        "mailbox_id": mailbox_id,
    }


# ---------------------------------------------------------------------------
# 25. POST /recovery/{mailbox_id}/start
# ---------------------------------------------------------------------------

@router.post("/recovery/{mailbox_id}/start")
async def start_recovery_endpoint(
    mailbox_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
):
    """Start auto-recovery for a specific mailbox (Admin only)."""
    mailbox = db.query(SenderMailbox).filter(SenderMailbox.mailbox_id == mailbox_id).first()
    if not mailbox:
        raise HTTPException(status_code=404, detail="Mailbox not found")

    result = start_recovery(mailbox_id, db)
    return {
        "message": "Recovery started",
        "mailbox_id": mailbox_id,
        "result": result,
    }


# ---------------------------------------------------------------------------
# 26. GET /export
# ---------------------------------------------------------------------------

@router.get("/export")
async def export_report(
    format: str = Query("csv", pattern="^(csv|json)$"),
    mailbox_ids: Optional[str] = Query(None, description="Comma-separated mailbox IDs"),
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR])),
):
    """Export warmup report as CSV or JSON."""
    parsed_ids: Optional[List[int]] = None
    if mailbox_ids:
        try:
            parsed_ids = [int(x.strip()) for x in mailbox_ids.split(",") if x.strip()]
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid mailbox_ids format")

    if format == "csv":
        csv_data = export_csv(parsed_ids, days, db)
        stream = io.StringIO(csv_data)
        return StreamingResponse(
            iter([stream.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=warmup_report.csv"},
        )
    else:
        json_data = export_json(parsed_ids, days, db)
        return StreamingResponse(
            iter([json_data]),
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=warmup_report.json"},
        )


# ---------------------------------------------------------------------------
# 27. GET /scheduler/status
# ---------------------------------------------------------------------------

@router.get("/scheduler/status")
async def get_scheduler_status_endpoint(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR])),
):
    """Get the current warmup scheduler status."""
    status = get_scheduler_status()
    return status
