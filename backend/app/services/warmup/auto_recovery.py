"""Auto-Recovery Service - gradual resume after pause."""
import json
from datetime import datetime, timedelta
from typing import Dict, Any
from sqlalchemy.orm import Session

from app.db.models.sender_mailbox import SenderMailbox, WarmupStatus
from app.db.models.warmup_alert import WarmupAlert, AlertType, AlertSeverity
from app.core.settings_resolver import get_tenant_setting


def check_recovery_eligibility(mailbox: SenderMailbox, db: Session, tenant_id=None) -> bool:
    if mailbox.warmup_status not in [WarmupStatus.PAUSED, WarmupStatus.BLACKLISTED]:
        return False
    wait_days = int(get_tenant_setting(db, "warmup_recovery_wait_days", tenant_id=tenant_id, default=3))
    if not mailbox.updated_at:
        return False
    days_paused = (datetime.utcnow() - mailbox.updated_at).days
    return days_paused >= wait_days


def start_recovery(mailbox_id: int, db: Session) -> Dict[str, Any]:
    mailbox = db.query(SenderMailbox).filter(SenderMailbox.mailbox_id == mailbox_id).first()
    if not mailbox:
        return {"error": "Mailbox not found"}

    mailbox.warmup_status = WarmupStatus.RECOVERING
    mailbox.auto_recovery_started_at = datetime.utcnow()
    mailbox.warmup_days_completed = 0
    mailbox.daily_send_limit = 2
    mailbox.emails_sent_today = 0

    alert = WarmupAlert(
        mailbox_id=mailbox_id,
        alert_type=AlertType.AUTO_RECOVERED,
        severity=AlertSeverity.INFO,
        title=f"Recovery started for {mailbox.email}",
        message=f"Auto-recovery initiated. Mailbox will gradually ramp up sending volume.",
    )
    db.add(alert)
    db.commit()

    return {"mailbox_id": mailbox_id, "status": "recovering", "daily_limit": 2}


def advance_recovery(mailbox: SenderMailbox, db: Session, tenant_id=None) -> Dict[str, Any]:
    if mailbox.warmup_status != WarmupStatus.RECOVERING:
        return {"skipped": True}

    ramp_factor = float(get_tenant_setting(db, "warmup_recovery_ramp_factor", tenant_id=tenant_id, default=1.5))
    new_limit = max(2, int(mailbox.daily_send_limit * ramp_factor))
    mailbox.daily_send_limit = min(new_limit, 35)
    mailbox.warmup_days_completed += 1

    if mailbox.daily_send_limit >= 25 and mailbox.warmup_days_completed >= 7:
        return complete_recovery(mailbox, db)

    db.commit()
    return {"mailbox_id": mailbox.mailbox_id, "day": mailbox.warmup_days_completed, "new_limit": mailbox.daily_send_limit}


def complete_recovery(mailbox: SenderMailbox, db: Session) -> Dict[str, Any]:
    mailbox.warmup_status = WarmupStatus.WARMING_UP
    mailbox.auto_recovery_started_at = None

    alert = WarmupAlert(
        mailbox_id=mailbox.mailbox_id,
        alert_type=AlertType.AUTO_RECOVERED,
        severity=AlertSeverity.INFO,
        title=f"Recovery complete for {mailbox.email}",
        message=f"Mailbox has been restored to WARMING_UP status.",
    )
    db.add(alert)
    db.commit()

    return {"mailbox_id": mailbox.mailbox_id, "status": "warming_up", "recovery_complete": True}


def run_auto_recovery_check(db: Session, tenant_id=None) -> Dict[str, Any]:
    enabled = get_tenant_setting(db, "warmup_auto_recovery_enabled", tenant_id=tenant_id, default=True)
    if not enabled:
        return {"skipped": True, "reason": "Auto-recovery disabled"}

    recovering = db.query(SenderMailbox).filter(SenderMailbox.warmup_status == WarmupStatus.RECOVERING).all()
    for mb in recovering:
        advance_recovery(mb, db, tenant_id=tenant_id)

    paused = db.query(SenderMailbox).filter(
        SenderMailbox.warmup_status.in_([WarmupStatus.PAUSED, WarmupStatus.BLACKLISTED])
    ).all()
    auto_started = 0
    for mb in paused:
        if check_recovery_eligibility(mb, db, tenant_id=tenant_id):
            start_recovery(mb.mailbox_id, db)
            auto_started += 1

    return {"recovering_advanced": len(recovering), "auto_started": auto_started}
