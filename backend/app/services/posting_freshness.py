"""Pure job-posting freshness filters for lead sourcing.

These helpers decide whether a sourced job posting should be dropped because it
is *stale* (older than an allowed age) or *expired* (the source told us the offer
has closed). They are the freshness counterpart to ``company_filters`` and follow
the same recall-preserving contract:

    Unknown / unparseable dates are NEVER dropped — recall is preserved and the
    ambiguity is resolved downstream, not by discarding a possibly-good lead.

Kept dependency-free and side-effect-free so they can be unit-tested in isolation
and reused by the pipeline.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional


def coerce_date(value) -> Optional[date]:
    """Best-effort parse of a ``date`` from a date/datetime/ISO string.

    Returns ``None`` when nothing sensible can be parsed (blank, malformed,
    non-date types). A ``datetime`` collapses to its date; a trailing ``Z`` (UTC)
    is tolerated on ISO strings.

    Examples:
        date(2026, 7, 1)          -> date(2026, 7, 1)
        datetime(2026, 7, 1, 9)   -> date(2026, 7, 1)
        "2026-07-01"              -> date(2026, 7, 1)
        "2026-07-01T09:30:00Z"    -> date(2026, 7, 1)
        "" / None / "n/a" / 123   -> None
    """
    if value is None:
        return None
    # bool is an int subclass — guard so True/False never look like a date.
    if isinstance(value, bool):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value

    text = str(value).strip()
    if not text:
        return None
    text = text.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text).date()
    except (ValueError, TypeError):
        pass
    # Fall back to a bare date prefix ("2026-07-01 ...").
    try:
        return datetime.fromisoformat(text[:10]).date()
    except (ValueError, TypeError):
        return None


def posting_too_old(posting_value, max_age_days: int, today: Optional[date] = None) -> bool:
    """True when a KNOWN posting date is older than ``max_age_days``.

    Recall-preserving: an unknown/unparseable posting date returns False, and a
    non-positive ``max_age_days`` disables the gate entirely. A future-dated
    posting (clock skew / bad data) is never considered stale.
    """
    if not max_age_days or max_age_days <= 0:
        return False
    posted = coerce_date(posting_value)
    if posted is None:
        return False
    ref = today or date.today()
    return (ref - posted).days > max_age_days


def posting_expired(expiration_value, today: Optional[date] = None) -> bool:
    """True when a KNOWN expiration date is strictly in the past.

    Recall-preserving: an unknown/unparseable expiration returns False. Only
    sources that actually report an offer-expiration date (e.g. JSearch) trigger
    this; everyone else simply omits the field and is never dropped by it.
    """
    expires = coerce_date(expiration_value)
    if expires is None:
        return False
    ref = today or date.today()
    return expires < ref
