"""Per-recipient-domain send throttling service.

Tracks how many emails have been sent to each recipient domain (e.g.,
gmail.com, company.com) per day across ALL mailboxes for a tenant, and
enforces configurable daily limits.

This protects domain reputation by preventing too many emails from
landing at a single provider on the same day — a key signal that
ESPs use to flag senders as spammers.
"""
from datetime import datetime, date
from typing import Dict, Optional, Tuple

import structlog
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models.contact import ContactDetails
from app.db.models.outreach import OutreachEvent, OutreachStatus
from app.core.settings_resolver import get_tenant_setting

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAJOR_PROVIDER_DOMAINS: set = {
    "gmail.com",
    "outlook.com",
    "hotmail.com",
    "yahoo.com",
    "aol.com",
    "icloud.com",
    "live.com",
    "msn.com",
    "googlemail.com",
}

DEFAULT_DOMAIN_DAILY_LIMIT: int = 50
MAJOR_PROVIDER_DAILY_LIMIT: int = 30


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_domain(email: str) -> str:
    """Extract the lowercased domain from an email address.

    Returns empty string if the email is malformed.
    """
    if not email or "@" not in email:
        return ""
    return email.rsplit("@", 1)[1].strip().lower()


def _get_limit_for_domain(
    domain: str,
    db: Session,
    tenant_id: Optional[int] = None,
) -> int:
    """Return the daily send limit for a given recipient domain.

    Resolution order:
    1. Tenant/global setting ``domain_daily_limit_major_providers`` (for
       major providers) or ``domain_daily_limit_default`` (for everything
       else).
    2. Module-level constants as fallback.
    """
    if domain in MAJOR_PROVIDER_DOMAINS:
        setting_val = get_tenant_setting(
            db,
            "domain_daily_limit_major_providers",
            tenant_id=tenant_id,
            default=None,
        )
        if setting_val is not None:
            try:
                return int(setting_val)
            except (TypeError, ValueError):
                pass
        return MAJOR_PROVIDER_DAILY_LIMIT

    # General / corporate domain
    setting_val = get_tenant_setting(
        db,
        "domain_daily_limit_default",
        tenant_id=tenant_id,
        default=None,
    )
    if setting_val is not None:
        try:
            return int(setting_val)
        except (TypeError, ValueError):
            pass
    return DEFAULT_DOMAIN_DAILY_LIMIT


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def check_domain_throttle(
    db: Session,
    recipient_email: str,
    tenant_id: int,
) -> Tuple[bool, str]:
    """Check whether another email can be sent to ``recipient_email``'s
    domain today without breaching the per-domain daily limit.

    Args:
        db: Active SQLAlchemy session.
        recipient_email: The intended recipient's email address.
        tenant_id: The tenant performing the send.

    Returns:
        ``(allowed, reason)`` — *allowed* is ``True`` when the send may
        proceed; *reason* explains why it was blocked (empty when allowed).
    """
    domain = _extract_domain(recipient_email)
    if not domain:
        # Cannot determine domain — allow the send and let downstream
        # validation catch the bad address.
        return True, ""

    limit = _get_limit_for_domain(domain, db, tenant_id=tenant_id)

    # sent_at is stored in UTC; use the UTC date so the daily window is correct
    # regardless of the server's local timezone.
    today_start = datetime.combine(datetime.utcnow().date(), datetime.min.time())

    # Count SENT outreach events today whose contact email ends with
    # @<domain>.  We join ContactDetails to inspect the email column.
    sent_today = (
        db.query(func.count(OutreachEvent.event_id))
        .join(
            ContactDetails,
            ContactDetails.contact_id == OutreachEvent.contact_id,
        )
        .filter(
            OutreachEvent.tenant_id == tenant_id,
            OutreachEvent.status == OutreachStatus.SENT,
            OutreachEvent.sent_at >= today_start,
            func.lower(ContactDetails.email).like(f"%@{domain}"),
        )
        .scalar()
    ) or 0

    if sent_today >= limit:
        reason = (
            f"Domain throttle: {sent_today}/{limit} emails already sent "
            f"to @{domain} today"
        )
        logger.info(
            "Domain throttle hit",
            domain=domain,
            sent_today=sent_today,
            limit=limit,
            tenant_id=tenant_id,
        )
        return False, reason

    return True, ""


def get_domain_send_counts(
    db: Session,
    tenant_id: int,
    target_date: Optional[date] = None,
) -> Dict[str, int]:
    """Return ``{domain: count}`` of emails sent per recipient domain on
    the given date (defaults to today).

    Useful for admin dashboards and diagnostics.

    Args:
        db: Active SQLAlchemy session.
        tenant_id: Scope to this tenant's outreach events.
        target_date: The calendar date to inspect (default: today UTC).

    Returns:
        Dictionary mapping each recipient domain to the number of SENT
        outreach events for that date.
    """
    if target_date is None:
        # sent_at is stored in UTC (datetime.utcnow); default the window to the
        # UTC calendar date so it stays consistent regardless of server timezone.
        target_date = datetime.utcnow().date()

    day_start = datetime.combine(target_date, datetime.min.time())
    day_end = datetime.combine(target_date, datetime.max.time())

    # We need the domain part of the contact's email.  SQLAlchemy's
    # ``func.substring_index`` works on MySQL; for SQLite (tests) we fall
    # back to Python-side aggregation.
    rows = (
        db.query(
            ContactDetails.email,
        )
        .join(
            OutreachEvent,
            OutreachEvent.contact_id == ContactDetails.contact_id,
        )
        .filter(
            OutreachEvent.tenant_id == tenant_id,
            OutreachEvent.status == OutreachStatus.SENT,
            OutreachEvent.sent_at >= day_start,
            OutreachEvent.sent_at <= day_end,
        )
        .all()
    )

    counts: Dict[str, int] = {}
    for (email,) in rows:
        domain = _extract_domain(email or "")
        if domain:
            counts[domain] = counts.get(domain, 0) + 1

    return counts
