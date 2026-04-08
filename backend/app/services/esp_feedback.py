"""ESP Feedback Loop (FBL) monitoring service.

Tracks complaint rates per mailbox and auto-pauses mailboxes that exceed
the configurable complaint-rate threshold (default 0.3%).
"""

from typing import Optional

import structlog
from sqlalchemy.orm import Session

from app.db.models.sender_mailbox import SenderMailbox
from app.core.settings_resolver import get_tenant_setting
from app.db.query_helpers import tenant_filter

logger = structlog.get_logger(__name__)

# Default complaint rate threshold (0.3%)
DEFAULT_COMPLAINT_RATE_THRESHOLD = 0.003


def record_complaint(
    db: Session,
    mailbox_id: int,
    tenant_id: int,
    email: str,
    reason: Optional[str] = None,
) -> None:
    """Record a complaint (FBL report) against a mailbox.

    Increments the complaint_count on the SenderMailbox and logs the event.

    Args:
        db: Database session.
        mailbox_id: The sender mailbox that received the complaint.
        tenant_id: Tenant scope.
        email: The recipient email address that filed the complaint.
        reason: Optional reason/category from the FBL report (e.g. "abuse", "spam").
    """
    mailbox = (
        db.query(SenderMailbox)
        .filter(
            SenderMailbox.mailbox_id == mailbox_id,
            SenderMailbox.tenant_id == tenant_id,
        )
        .first()
    )

    if not mailbox:
        logger.warning(
            "esp_complaint_mailbox_not_found",
            mailbox_id=mailbox_id,
            tenant_id=tenant_id,
            complainant_email=email,
        )
        return

    mailbox.complaint_count = (mailbox.complaint_count or 0) + 1
    db.flush()

    logger.info(
        "esp_complaint_recorded",
        mailbox_id=mailbox_id,
        mailbox_email=mailbox.email,
        tenant_id=tenant_id,
        complainant_email=email,
        reason=reason,
        complaint_count=mailbox.complaint_count,
    )

    # Check if the mailbox should be auto-paused after this complaint
    rate, is_healthy = check_complaint_rate(db, mailbox_id, tenant_id=tenant_id)
    if not is_healthy:
        logger.warning(
            "esp_complaint_auto_pause_triggered",
            mailbox_id=mailbox_id,
            mailbox_email=mailbox.email,
            complaint_rate=rate,
        )


def check_complaint_rate(
    db: Session,
    mailbox_id: int,
    tenant_id: Optional[int] = None,
) -> tuple[float, bool]:
    """Check the complaint rate for a mailbox and auto-pause if unhealthy.

    Complaint rate = complaint_count / total_emails_sent.
    If rate exceeds the configurable threshold, the mailbox is deactivated.

    Args:
        db: Database session.
        mailbox_id: The mailbox to check.
        tenant_id: Optional tenant scope for loading the threshold setting.

    Returns:
        A tuple of (rate, is_healthy).
        rate: Float complaint rate (0.0 to 1.0).
        is_healthy: True if rate is at or below threshold, False otherwise.
    """
    mailbox = db.query(SenderMailbox).filter(
        SenderMailbox.mailbox_id == mailbox_id,
    ).first()

    if not mailbox:
        logger.warning(
            "esp_check_mailbox_not_found",
            mailbox_id=mailbox_id,
        )
        return 0.0, True

    total_sent = mailbox.total_emails_sent or 0
    complaint_count = mailbox.complaint_count or 0

    if total_sent == 0:
        return 0.0, True

    rate = complaint_count / total_sent

    # Resolve threshold: tenant setting > global setting > default
    effective_tenant_id = tenant_id if tenant_id is not None else mailbox.tenant_id
    threshold = get_tenant_setting(
        db,
        "complaint_rate_threshold",
        tenant_id=effective_tenant_id,
        default=DEFAULT_COMPLAINT_RATE_THRESHOLD,
    )

    # Coerce to float in case it comes back as a string
    try:
        threshold = float(threshold)
    except (TypeError, ValueError):
        threshold = DEFAULT_COMPLAINT_RATE_THRESHOLD

    is_healthy = rate <= threshold

    if not is_healthy:
        # Auto-pause the mailbox
        mailbox.is_active = False
        db.flush()

        logger.warning(
            "esp_mailbox_auto_paused",
            mailbox_id=mailbox_id,
            mailbox_email=mailbox.email,
            tenant_id=mailbox.tenant_id,
            complaint_rate=round(rate, 6),
            threshold=threshold,
            complaint_count=complaint_count,
            total_sent=total_sent,
        )

    return round(rate, 6), is_healthy


def get_complaint_stats(
    db: Session,
    tenant_id: Optional[int] = None,
) -> list[dict]:
    """Get per-mailbox complaint statistics for the admin dashboard.

    Args:
        db: Database session.
        tenant_id: Tenant scope. None returns all tenants (super admin).

    Returns:
        List of dicts with mailbox complaint stats, sorted by complaint
        rate descending (worst offenders first).
    """
    query = db.query(SenderMailbox)
    query = tenant_filter(query, SenderMailbox, tenant_id)
    mailboxes = query.all()

    stats = []
    for m in mailboxes:
        total_sent = m.total_emails_sent or 0
        complaint_count = m.complaint_count or 0
        rate = (complaint_count / total_sent) if total_sent > 0 else 0.0

        stats.append({
            "mailbox_id": m.mailbox_id,
            "email": m.email,
            "tenant_id": m.tenant_id,
            "is_active": m.is_active,
            "total_emails_sent": total_sent,
            "complaint_count": complaint_count,
            "complaint_rate": round(rate, 6),
            "is_healthy": rate <= DEFAULT_COMPLAINT_RATE_THRESHOLD,
        })

    # Sort by complaint rate descending so worst offenders are first
    stats.sort(key=lambda x: x["complaint_rate"], reverse=True)

    return stats
