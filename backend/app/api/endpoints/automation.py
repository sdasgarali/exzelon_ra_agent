"""Automation Activity API — exposes system automation events to users."""
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, Query, Body
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from app.api.deps.database import get_db
from app.api.deps.auth import get_current_active_user, require_role
from app.db.models.user import User, UserRole
from app.db.models.automation_event import AutomationEvent
from app.db.models.settings import Settings

router = APIRouter(prefix="/automation", tags=["automation"])

# ─── Job Registry ────────────────────────────────────────────────────────────
# Metadata for all 17 scheduler jobs, grouped into 5 categories.

JOB_REGISTRY = [
    # Warmup Engine (9 jobs)
    {"id": "daily_assessment", "name": "Daily Warmup Assessment", "group": "Warmup Engine", "schedule": "Daily 00:05 UTC"},
    {"id": "peer_warmup_cycle", "name": "Peer Warmup Cycle", "group": "Warmup Engine", "schedule": "Hourly 9am-5pm UTC"},
    {"id": "auto_reply_cycle", "name": "Auto Reply Cycle", "group": "Warmup Engine", "schedule": "Hourly :30 9am-5pm UTC"},
    {"id": "daily_count_reset", "name": "Daily Count Reset", "group": "Warmup Engine", "schedule": "Daily 00:00 UTC"},
    {"id": "dns_checks", "name": "DNS Health Checks", "group": "Warmup Engine", "schedule": "Every 12 hours"},
    {"id": "blacklist_checks", "name": "Blacklist Checks", "group": "Warmup Engine", "schedule": "Every 12 hours"},
    {"id": "daily_log_snapshot", "name": "Daily Log Snapshot", "group": "Warmup Engine", "schedule": "Daily 23:55 UTC"},
    {"id": "auto_recovery_check", "name": "Auto Recovery Check", "group": "Warmup Engine", "schedule": "Daily 06:00 UTC"},
    {"id": "imap_read_cycle", "name": "IMAP Read Emulation", "group": "Warmup Engine", "schedule": "Every 30 minutes"},
    # Lead Pipeline (1 job)
    {"id": "lead_sourcing_run", "name": "Scheduled Lead Sourcing", "group": "Lead Pipeline", "schedule": "6x daily (every 4h UTC)"},
    # Campaign & Outreach (3 jobs)
    {"id": "campaign_processor", "name": "Campaign Sequence Processor", "group": "Campaign & Outreach", "schedule": "Every 2 minutes"},
    {"id": "inbox_sync", "name": "Inbox Sync", "group": "Campaign & Outreach", "schedule": "Every 5 min 8am-7pm UTC"},
    {"id": "check_outreach_replies", "name": "Check Outreach Replies", "group": "Campaign & Outreach", "schedule": "Every 15 min 8am-7pm UTC"},
    {"id": "auto_enrollment", "name": "Campaign Auto-Enrollment", "group": "Campaign & Outreach", "schedule": "Every 30 minutes"},
    # Intelligence (2 jobs)
    {"id": "lead_scoring", "name": "Daily Lead Scoring", "group": "Intelligence", "schedule": "Daily 03:00 UTC"},
    {"id": "crm_sync", "name": "Nightly CRM Sync", "group": "Intelligence", "schedule": "Daily 04:00 UTC"},
    # System (4 jobs)
    {"id": "daily_backup", "name": "Daily Database Backup", "group": "System", "schedule": "Daily 02:00 UTC"},
    {"id": "backup_cleanup", "name": "Backup Cleanup", "group": "System", "schedule": "Daily 02:30 UTC"},
    {"id": "cost_aggregation", "name": "Daily Cost Aggregation", "group": "System", "schedule": "Daily 23:45 UTC"},
    # Intelligence (3 jobs)
    {"id": "cost_analysis", "name": "Monthly Cost Analysis", "group": "Intelligence", "schedule": "1st of month 03:30 UTC"},
]


@router.get("/events")
def list_events(
    event_type: Optional[str] = None,
    status: Optional[str] = None,
    hours: int = Query(24, ge=1, le=168),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """List recent automation events (paginated, filterable)."""
    since = datetime.utcnow() - timedelta(hours=hours)
    query = db.query(AutomationEvent).filter(AutomationEvent.created_at >= since)

    if event_type:
        query = query.filter(AutomationEvent.event_type == event_type)
    if status:
        query = query.filter(AutomationEvent.status == status)

    total = query.count()
    events = query.order_by(desc(AutomationEvent.created_at)).offset(
        (page - 1) * page_size
    ).limit(page_size).all()

    return {
        "items": [
            {
                "event_id": e.event_id,
                "event_type": e.event_type,
                "source": e.source,
                "title": e.title,
                "details": json.loads(e.details_json) if e.details_json else None,
                "status": e.status,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in events
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size if total > 0 else 0,
    }


@router.get("/events/summary")
def events_summary(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """Last 24h summary — counts by event type and status."""
    since = datetime.utcnow() - timedelta(hours=24)
    rows = db.query(
        AutomationEvent.event_type,
        AutomationEvent.status,
        func.count(AutomationEvent.event_id),
    ).filter(
        AutomationEvent.created_at >= since,
    ).group_by(
        AutomationEvent.event_type,
        AutomationEvent.status,
    ).all()

    by_type: dict = {}
    total = 0
    errors = 0
    for event_type, status, count in rows:
        by_type.setdefault(event_type, {"total": 0, "success": 0, "error": 0, "skipped": 0})
        by_type[event_type]["total"] += count
        by_type[event_type][status] = by_type[event_type].get(status, 0) + count
        total += count
        if status == "error":
            errors += count

    # Latest event
    latest = db.query(AutomationEvent).filter(
        AutomationEvent.created_at >= since,
    ).order_by(desc(AutomationEvent.created_at)).first()

    return {
        "period_hours": 24,
        "total_events": total,
        "total_errors": errors,
        "by_type": by_type,
        "latest_event": {
            "title": latest.title,
            "event_type": latest.event_type,
            "status": latest.status,
            "created_at": latest.created_at.isoformat() if latest.created_at else None,
        } if latest else None,
    }


# ─── Automation Controls ─────────────────────────────────────────────────────


def _read_bool_setting(db: Session, key: str, default: bool) -> bool:
    row = db.query(Settings).filter(Settings.key == key).first()
    if row and row.value_json:
        try:
            return bool(json.loads(row.value_json))
        except (json.JSONDecodeError, TypeError):
            pass
    return default


def _upsert_bool_setting(db: Session, key: str, value: bool, updated_by: str):
    row = db.query(Settings).filter(Settings.key == key).first()
    val_json = json.dumps(value)
    if row:
        row.value_json = val_json
        row.updated_by = updated_by
    else:
        db.add(Settings(
            key=key, value_json=val_json, type="boolean",
            description=f"Automation toggle: {key}", updated_by=updated_by,
        ))


@router.get("/controls")
def get_controls(
    db: Session = Depends(get_db),
    user: User = Depends(require_role([UserRole.ADMIN])),
):
    """Return master toggle, chain toggles, and all 17 jobs with enabled state."""
    from app.services.warmup.scheduler import get_scheduler_status

    scheduler_status = get_scheduler_status()
    next_runs = {j["id"]: j["next_run"] for j in scheduler_status.get("jobs", [])}

    master_enabled = _read_bool_setting(db, "automation_master_enabled", True)
    chain_enrichment = _read_bool_setting(db, "automation_chain_enrichment", False)
    chain_validation = _read_bool_setting(db, "automation_chain_validation", False)
    chain_enrollment = _read_bool_setting(db, "automation_chain_enrollment", False)

    jobs = []
    for reg in JOB_REGISTRY:
        enabled = _read_bool_setting(db, f"automation_{reg['id']}_enabled", True)
        jobs.append({
            "id": reg["id"],
            "name": reg["name"],
            "group": reg["group"],
            "schedule": reg["schedule"],
            "enabled": enabled,
            "next_run": next_runs.get(reg["id"]),
        })

    return {
        "scheduler_running": scheduler_status.get("running", False),
        "master_enabled": master_enabled,
        "chain_enrichment": chain_enrichment,
        "chain_validation": chain_validation,
        "chain_enrollment": chain_enrollment,
        "jobs": jobs,
    }


@router.put("/controls")
def update_controls(
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_role([UserRole.ADMIN])),
):
    """Update master toggle, chain toggles, and/or per-job enabled states."""
    from app.services.automation_logger import log_automation_event

    changes = []

    if "master_enabled" in payload:
        old = _read_bool_setting(db, "automation_master_enabled", True)
        new_val = bool(payload["master_enabled"])
        if old != new_val:
            _upsert_bool_setting(db, "automation_master_enabled", new_val, user.email)
            changes.append(f"master: {old} → {new_val}")

    if "chain_enrichment" in payload:
        old = _read_bool_setting(db, "automation_chain_enrichment", False)
        new_val = bool(payload["chain_enrichment"])
        if old != new_val:
            _upsert_bool_setting(db, "automation_chain_enrichment", new_val, user.email)
            changes.append(f"chain_enrichment: {old} → {new_val}")

    if "chain_validation" in payload:
        old = _read_bool_setting(db, "automation_chain_validation", False)
        new_val = bool(payload["chain_validation"])
        if old != new_val:
            _upsert_bool_setting(db, "automation_chain_validation", new_val, user.email)
            changes.append(f"chain_validation: {old} → {new_val}")

    if "chain_enrollment" in payload:
        old = _read_bool_setting(db, "automation_chain_enrollment", False)
        new_val = bool(payload["chain_enrollment"])
        if old != new_val:
            _upsert_bool_setting(db, "automation_chain_enrollment", new_val, user.email)
            changes.append(f"chain_enrollment: {old} → {new_val}")

    valid_ids = {r["id"] for r in JOB_REGISTRY}
    jobs_payload = payload.get("jobs", {})
    if isinstance(jobs_payload, dict):
        for job_id, enabled in jobs_payload.items():
            if job_id not in valid_ids:
                continue
            key = f"automation_{job_id}_enabled"
            old = _read_bool_setting(db, key, True)
            new_val = bool(enabled)
            if old != new_val:
                _upsert_bool_setting(db, key, new_val, user.email)
                changes.append(f"{job_id}: {old} → {new_val}")

    db.commit()

    if changes:
        log_automation_event(
            db, "automation_controls",
            f"Automation controls updated by {user.email}: {', '.join(changes[:5])}{'...' if len(changes) > 5 else ''}",
            details={"changes": changes, "updated_by": user.email},
            source="user",
        )

    return {"ok": True, "changes": changes}
