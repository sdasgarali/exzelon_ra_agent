"""Warmup Engine - Automated mailbox warmup management."""
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple
import structlog

from app.db.base import SessionLocal
from app.db.models.sender_mailbox import SenderMailbox, WarmupStatus
from app.db.models.job_run import JobRun, JobStatus
from app.core.settings_resolver import get_tenant_setting

logger = structlog.get_logger()

PHASE_NAMES = {
    1: "Initial",
    2: "Building Trust",
    3: "Scaling Up",
    4: "Full Ramp",
}


def load_warmup_config(db, tenant_id=None) -> Dict[str, Any]:
    """Load all warmup settings from Settings table into a config dict."""
    config = {
        "phase_1_days": int(get_tenant_setting(db, "warmup_phase_1_days", tenant_id=tenant_id, default=7)),
        "phase_1_min_emails": int(get_tenant_setting(db, "warmup_phase_1_min_emails", tenant_id=tenant_id, default=2)),
        "phase_1_max_emails": int(get_tenant_setting(db, "warmup_phase_1_max_emails", tenant_id=tenant_id, default=5)),
        "phase_2_days": int(get_tenant_setting(db, "warmup_phase_2_days", tenant_id=tenant_id, default=7)),
        "phase_2_min_emails": int(get_tenant_setting(db, "warmup_phase_2_min_emails", tenant_id=tenant_id, default=5)),
        "phase_2_max_emails": int(get_tenant_setting(db, "warmup_phase_2_max_emails", tenant_id=tenant_id, default=15)),
        "phase_3_days": int(get_tenant_setting(db, "warmup_phase_3_days", tenant_id=tenant_id, default=7)),
        "phase_3_min_emails": int(get_tenant_setting(db, "warmup_phase_3_min_emails", tenant_id=tenant_id, default=15)),
        "phase_3_max_emails": int(get_tenant_setting(db, "warmup_phase_3_max_emails", tenant_id=tenant_id, default=25)),
        "phase_4_days": int(get_tenant_setting(db, "warmup_phase_4_days", tenant_id=tenant_id, default=9)),
        "phase_4_min_emails": int(get_tenant_setting(db, "warmup_phase_4_min_emails", tenant_id=tenant_id, default=25)),
        "phase_4_max_emails": int(get_tenant_setting(db, "warmup_phase_4_max_emails", tenant_id=tenant_id, default=35)),
        "bounce_rate_good": float(get_tenant_setting(db, "warmup_bounce_rate_good", tenant_id=tenant_id, default=2.0)),
        "bounce_rate_bad": float(get_tenant_setting(db, "warmup_bounce_rate_bad", tenant_id=tenant_id, default=5.0)),
        "reply_rate_good": float(get_tenant_setting(db, "warmup_reply_rate_good", tenant_id=tenant_id, default=10.0)),
        "complaint_rate_bad": float(get_tenant_setting(db, "warmup_complaint_rate_bad", tenant_id=tenant_id, default=0.1)),
        "weight_bounce_rate": int(get_tenant_setting(db, "warmup_weight_bounce_rate", tenant_id=tenant_id, default=35)),
        "weight_reply_rate": int(get_tenant_setting(db, "warmup_weight_reply_rate", tenant_id=tenant_id, default=25)),
        "weight_complaint_rate": int(get_tenant_setting(db, "warmup_weight_complaint_rate", tenant_id=tenant_id, default=25)),
        "weight_age": int(get_tenant_setting(db, "warmup_weight_age", tenant_id=tenant_id, default=15)),
        "auto_pause_bounce_rate": float(get_tenant_setting(db, "warmup_auto_pause_bounce_rate", tenant_id=tenant_id, default=5.0)),
        "auto_pause_complaint_rate": float(get_tenant_setting(db, "warmup_auto_pause_complaint_rate", tenant_id=tenant_id, default=0.3)),
        "min_emails_for_scoring": int(get_tenant_setting(db, "warmup_min_emails_for_scoring", tenant_id=tenant_id, default=10)),
        "active_health_threshold": int(get_tenant_setting(db, "warmup_active_health_threshold", tenant_id=tenant_id, default=80)),
        "active_min_days": int(get_tenant_setting(db, "warmup_active_min_days", tenant_id=tenant_id, default=7)),
        "total_days": int(get_tenant_setting(db, "warmup_total_days", tenant_id=tenant_id, default=30)),
        "daily_increment": float(get_tenant_setting(db, "warmup_daily_increment", tenant_id=tenant_id, default=1.0)),
    }
    return config


def get_warmup_phase(day: int, config: Dict[str, Any]) -> Tuple[int, str]:
    """Determine phase (1-4) and name for a given warmup day."""
    p1_end = config["phase_1_days"]
    p2_end = p1_end + config["phase_2_days"]
    p3_end = p2_end + config["phase_3_days"]

    if day <= p1_end:
        return 1, PHASE_NAMES[1]
    elif day <= p2_end:
        return 2, PHASE_NAMES[2]
    elif day <= p3_end:
        return 3, PHASE_NAMES[3]
    else:
        return 4, PHASE_NAMES[4]


def get_daily_limit_for_day(day: int, config: Dict[str, Any]) -> int:
    """Linear interpolation within phase to get daily email limit."""
    phase, _ = get_warmup_phase(day, config)

    phase_days = config[f"phase_{phase}_days"]
    min_emails = config[f"phase_{phase}_min_emails"]
    max_emails = config[f"phase_{phase}_max_emails"]

    # Calculate day within this phase
    phase_start = 0
    for p in range(1, phase):
        phase_start += config[f"phase_{p}_days"]

    day_in_phase = day - phase_start
    if phase_days <= 1:
        return max_emails

    # Linear interpolation
    progress = (day_in_phase - 1) / (phase_days - 1)
    limit = min_emails + progress * (max_emails - min_emails)
    return max(1, round(limit))


def calculate_health_score(mailbox: SenderMailbox, config: Dict[str, Any]) -> Dict[str, float]:
    """Calculate health score (0-100) based on weighted metrics."""
    total_sent = mailbox.total_emails_sent or 0

    bounce_rate = (mailbox.bounce_count / total_sent * 100) if total_sent > 0 else 0.0
    reply_rate = (mailbox.reply_count / total_sent * 100) if total_sent > 0 else 0.0
    complaint_rate = (mailbox.complaint_count / total_sent * 100) if total_sent > 0 else 0.0

    age_days = 0
    if mailbox.created_at:
        age_days = (datetime.utcnow() - mailbox.created_at).days

    # Bounce rate score (lower is better)
    good = config["bounce_rate_good"]
    bad = config["bounce_rate_bad"]
    if bounce_rate <= good:
        bounce_score = 100.0
    elif bounce_rate >= bad:
        bounce_score = 0.0
    else:
        bounce_score = 100.0 * (1 - (bounce_rate - good) / (bad - good))

    # Reply rate score (higher is better)
    reply_good = config["reply_rate_good"]
    if reply_rate >= reply_good:
        reply_score = 100.0
    elif reply_rate <= 0:
        reply_score = 0.0
    else:
        reply_score = 100.0 * (reply_rate / reply_good)

    # Complaint rate score (lower is better)
    complaint_bad = config["complaint_rate_bad"]
    if complaint_rate <= 0:
        complaint_score = 100.0
    elif complaint_rate >= complaint_bad:
        complaint_score = 0.0
    else:
        complaint_score = 100.0 * (1 - complaint_rate / complaint_bad)

    # Age score (older is better, capped at 90 days)
    if age_days >= 90:
        age_score = 100.0
    else:
        age_score = 100.0 * (age_days / 90.0)

    # Weighted total
    w_bounce = config["weight_bounce_rate"]
    w_reply = config["weight_reply_rate"]
    w_complaint = config["weight_complaint_rate"]
    w_age = config["weight_age"]
    total_weight = w_bounce + w_reply + w_complaint + w_age

    health_score = (
        bounce_score * w_bounce +
        reply_score * w_reply +
        complaint_score * w_complaint +
        age_score * w_age
    ) / total_weight if total_weight > 0 else 0.0

    return {
        "health_score": round(health_score, 1),
        "bounce_score": round(bounce_score, 1),
        "reply_score": round(reply_score, 1),
        "complaint_score": round(complaint_score, 1),
        "age_score": round(age_score, 1),
        "bounce_rate": round(bounce_rate, 2),
        "reply_rate": round(reply_rate, 2),
        "complaint_rate": round(complaint_rate, 3),
        "account_age_days": age_days,
    }


def assess_mailbox(mailbox: SenderMailbox, config: Dict[str, Any], db) -> Dict[str, Any]:
    """Assess a single mailbox and apply status transitions."""
    result = {
        "mailbox_id": mailbox.mailbox_id,
        "email": mailbox.email,
        "old_status": mailbox.warmup_status.value,
        "new_status": mailbox.warmup_status.value,
        "action": "no_change",
        "health_score": 0.0,
        "daily_limit": mailbox.daily_send_limit,
    }

    health = calculate_health_score(mailbox, config)
    result["health_score"] = health["health_score"]
    total_sent = mailbox.total_emails_sent or 0

    # Auto-pause check: only after minimum emails sent
    if total_sent >= config["min_emails_for_scoring"]:
        bounce_rate = health["bounce_rate"]
        complaint_rate = health["complaint_rate"]

        if bounce_rate > config["auto_pause_bounce_rate"] or complaint_rate > config["auto_pause_complaint_rate"]:
            if mailbox.warmup_status != WarmupStatus.PAUSED:
                mailbox.warmup_status = WarmupStatus.PAUSED
                result["new_status"] = "paused"
                reason = []
                if bounce_rate > config["auto_pause_bounce_rate"]:
                    reason.append(f"bounce_rate={bounce_rate:.1f}%")
                if complaint_rate > config["auto_pause_complaint_rate"]:
                    reason.append(f"complaint_rate={complaint_rate:.3f}%")
                result["action"] = "auto_paused (" + ", ".join(reason) + ")"
                db.add(mailbox)
                return result

    current = mailbox.warmup_status

    if current == WarmupStatus.INACTIVE:
        if mailbox.is_active:
            mailbox.warmup_status = WarmupStatus.WARMING_UP
            mailbox.warmup_started_at = datetime.utcnow()
            mailbox.warmup_days_completed = 0
            mailbox.daily_send_limit = get_daily_limit_for_day(1, config)
            result["new_status"] = "warming_up"
            result["action"] = "started_warmup"
            result["daily_limit"] = mailbox.daily_send_limit

    elif current == WarmupStatus.WARMING_UP:
        day = (mailbox.warmup_days_completed or 0) + 1
        total_days = config["total_days"]

        if day > total_days:
            mailbox.warmup_status = WarmupStatus.COLD_READY
            mailbox.warmup_completed_at = datetime.utcnow()
            result["new_status"] = "cold_ready"
            result["action"] = "warmup_completed"
        else:
            new_limit = get_daily_limit_for_day(day, config)
            mailbox.daily_send_limit = new_limit
            mailbox.warmup_days_completed = day
            result["daily_limit"] = new_limit
            phase, phase_name = get_warmup_phase(day, config)
            result["action"] = f"day_{day}_phase_{phase}_{phase_name}"

    elif current == WarmupStatus.COLD_READY:
        days_since_ready = 0
        if mailbox.warmup_completed_at:
            days_since_ready = (datetime.utcnow() - mailbox.warmup_completed_at).days

        if (days_since_ready >= config["active_min_days"] and
                health["health_score"] >= config["active_health_threshold"] and
                total_sent >= config["min_emails_for_scoring"]):
            mailbox.warmup_status = WarmupStatus.ACTIVE
            result["new_status"] = "active"
            result["action"] = "promoted_to_active"

    db.add(mailbox)
    return result


def run_warmup_assessment(
    triggered_by: str = "system",
    mailbox_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Pipeline entry: assess all or one mailbox. Creates a JobRun record."""
    db = SessionLocal()
    job = None
    try:
        job = JobRun(
            tenant_id=1,
            pipeline_name="warmup_assessment",
            started_at=datetime.utcnow(),
            status=JobStatus.RUNNING,
            triggered_by=triggered_by,
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        config = load_warmup_config(db)

        if mailbox_id:
            mailboxes = db.query(SenderMailbox).filter(
                SenderMailbox.mailbox_id == mailbox_id,
                SenderMailbox.connection_status == "successful",
            ).all()
        else:
            mailboxes = db.query(SenderMailbox).filter(
                SenderMailbox.is_active == True,
                SenderMailbox.connection_status == "successful",
            ).all()

        counters = {
            "assessed": 0,
            "status_changes": 0,
            "auto_paused": 0,
            "promoted": 0,
            "errors": 0,
        }
        details = []

        for mb in mailboxes:
            try:
                detail = assess_mailbox(mb, config, db)
                counters["assessed"] += 1
                if detail["old_status"] != detail["new_status"]:
                    counters["status_changes"] += 1
                if "auto_paused" in detail.get("action", ""):
                    counters["auto_paused"] += 1
                if "promoted" in detail.get("action", ""):
                    counters["promoted"] += 1
                details.append(detail)
            except Exception as e:
                counters["errors"] += 1
                details.append({
                    "mailbox_id": mb.mailbox_id,
                    "email": mb.email,
                    "action": f"error: {str(e)}",
                })
                logger.error("warmup_assess_error", mailbox_id=mb.mailbox_id, error=str(e))

        job.status = JobStatus.COMPLETED
        job.ended_at = datetime.utcnow()
        job.counters_json = json.dumps(counters)
        db.commit()

        return {
            "run_id": job.run_id,
            **counters,
            "details": details,
        }

    except Exception as e:
        logger.error("warmup_assessment_failed", error=str(e))
        try:
            if job:
                job.status = JobStatus.FAILED
                job.ended_at = datetime.utcnow()
                job.error_message = str(e)
                db.commit()
        except Exception:
            pass
        raise
    finally:
        db.close()


def build_warmup_schedule(config: Dict[str, Any]) -> Dict[str, Any]:
    """Build day-by-day schedule for visualization."""
    total_days = config["total_days"]
    phases = []
    schedule = []

    day_offset = 0
    for p in range(1, 5):
        p_days = config[f"phase_{p}_days"]
        phases.append({
            "phase": p,
            "name": PHASE_NAMES[p],
            "start_day": day_offset + 1,
            "end_day": day_offset + p_days,
            "days": p_days,
            "min_emails": config[f"phase_{p}_min_emails"],
            "max_emails": config[f"phase_{p}_max_emails"],
        })
        day_offset += p_days

    for day in range(1, total_days + 1):
        phase, phase_name = get_warmup_phase(day, config)
        limit = get_daily_limit_for_day(day, config)
        schedule.append({
            "day": day,
            "phase": phase,
            "phase_name": phase_name,
            "recommended_emails": limit,
        })

    return {
        "total_days": total_days,
        "phases": phases,
        "schedule": schedule,
    }
