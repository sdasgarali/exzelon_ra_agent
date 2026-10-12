"""Health-aware mailbox selection service.

Replaces simple round-robin mailbox selection with weighted scoring
based on DNS health, remaining quota, warmup maturity, deliverability,
and optionally engagement rate.
"""

import socket
import threading
import time
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Iterable, Optional

import structlog
from sqlalchemy import and_
from sqlalchemy import func as sa_func
from sqlalchemy.orm import Query, Session

from app.core.config import settings
from app.db.models.outreach import OutreachChannel, OutreachEvent, OutreachStatus
from app.db.models.sender_mailbox import EmailProvider, SenderMailbox, WarmupStatus
from app.services.warmup.domain_reputation import ISP_PROFILES, recommended_daily_ramp

logger = structlog.get_logger(__name__)

# Scoring weights (without engagement)
WEIGHT_HEALTH = 0.40
WEIGHT_QUOTA = 0.30
WEIGHT_WARMUP_AGE = 0.15
WEIGHT_DELIVERABILITY = 0.15

# Scoring weights (with engagement)
WEIGHT_QUOTA_WITH_ENGAGEMENT = 0.20
WEIGHT_ENGAGEMENT = 0.10

# Warmup maturity threshold in days
WARMUP_MATURITY_DAYS = 30

# Eligible warmup statuses for sending
ELIGIBLE_WARMUP_STATUSES = [WarmupStatus.COLD_READY, WarmupStatus.ACTIVE]


# ---------------------------------------------------------------------------
# D1 — Warmup gate for OUTREACH sends (warmup traffic itself is never gated)
# ---------------------------------------------------------------------------
#
# A status of cold_ready/active alone is not proof of warmup (it can be set by
# seeding or by hand), so outreach also requires real warmup history: enough
# days AND enough warmup emails actually sent.


def min_warmup_days() -> int:
    return max(int(getattr(settings, "MIN_WARMUP_DAYS", 14) or 0), 0)


def min_warmup_emails() -> int:
    return max(int(getattr(settings, "MIN_WARMUP_EMAILS", 50) or 0), 0)


def outreach_eligible_filter():
    """SQLAlchemy clause: mailbox status AND warmup history allow outreach sends."""
    return and_(
        SenderMailbox.warmup_status.in_(ELIGIBLE_WARMUP_STATUSES),
        sa_func.coalesce(SenderMailbox.warmup_days_completed, 0) >= min_warmup_days(),
        sa_func.coalesce(SenderMailbox.warmup_emails_sent, 0) >= min_warmup_emails(),
    )


def warmup_progress_reason(mailbox: SenderMailbox) -> Optional[str]:
    """Why the mailbox's warmup history is not yet enough for outreach (None = enough)."""
    days = int(mailbox.warmup_days_completed or 0)
    emails = int(mailbox.warmup_emails_sent or 0)
    need_days, need_emails = min_warmup_days(), min_warmup_emails()
    if days >= need_days and emails >= need_emails:
        return None
    return f"Warming up — {days}/{need_days} days, {emails}/{need_emails} emails"


def outreach_block_reason(mailbox: SenderMailbox) -> Optional[str]:
    """Human-readable reason the mailbox may not send outreach (None = eligible).

    Python mirror of ``outreach_eligible_filter`` (status + warmup history).
    """
    status = mailbox.warmup_status
    if status not in ELIGIBLE_WARMUP_STATUSES:
        label = getattr(status, "value", status) or "inactive"
        return f"Not outreach-ready (status: {label})"
    return warmup_progress_reason(mailbox)


def is_outreach_eligible(mailbox: SenderMailbox) -> bool:
    """Python mirror of ``outreach_eligible_filter``."""
    return outreach_block_reason(mailbox) is None


# ---------------------------------------------------------------------------
# D2 — ISP ramp during a mailbox's first RAMP_WINDOW_DAYS of real outreach
# ---------------------------------------------------------------------------

RAMP_WINDOW_DAYS = 30


def _real_outreach_filters():
    """OutreachEvent rows that were actually sent from a mailbox (not skips/mail-merge)."""
    return (
        OutreachEvent.status != OutreachStatus.SKIPPED,
        OutreachEvent.channel != OutreachChannel.MAILMERGE,
    )


def first_outreach_dates(db: Session, mailbox_ids: Iterable[int]) -> dict[int, datetime]:
    """Earliest real outreach send per mailbox, in ONE grouped query."""
    ids = [i for i in set(mailbox_ids) if i is not None]
    if not ids:
        return {}
    rows = (
        db.query(OutreachEvent.sender_mailbox_id, sa_func.min(OutreachEvent.sent_at))
        .filter(OutreachEvent.sender_mailbox_id.in_(ids), *_real_outreach_filters())
        .group_by(OutreachEvent.sender_mailbox_id)
        .all()
    )
    return {mid: first for mid, first in rows if first is not None}


def ramp_day(first_sent_at: Optional[datetime], today: Optional[date] = None) -> int:
    """1-based day of outreach history. No sends yet => today would be day 1."""
    if first_sent_at is None:
        return 1
    today = today or datetime.utcnow().date()
    return max((today - first_sent_at.date()).days + 1, 1)


def effective_daily_limit(
    mailbox: SenderMailbox,
    first_sent_at: Optional[datetime] = None,
    today: Optional[date] = None,
) -> int:
    """Daily outreach cap: ``daily_send_limit``, clamped to the ISP ramp in the first 30 days."""
    limit = int(mailbox.daily_send_limit or 0)
    day = ramp_day(first_sent_at, today)
    if day > RAMP_WINDOW_DAYS:
        return limit
    ramp = recommended_daily_ramp(day, email=mailbox.email or "", smtp_host=mailbox.smtp_host or "")
    return min(limit, ramp)


def mailbox_effective_daily_limit(db: Session, mailbox: SenderMailbox, today: Optional[date] = None) -> int:
    """``effective_daily_limit`` for one mailbox, looking up its first outreach date."""
    first = first_outreach_dates(db, [mailbox.mailbox_id]).get(mailbox.mailbox_id)
    return effective_daily_limit(mailbox, first, today)


# ---------------------------------------------------------------------------
# D3 — Per-IP cohort cap
# ---------------------------------------------------------------------------
#
# Sending domains whose SMTP host resolves to the same IP share that IP's
# reputation. Only MAX_LIVE_DOMAINS_PER_IP of them may be "live" (sent outreach in
# the last LIVE_WINDOW_DAYS) at once. Shared ESP infrastructure (Google /
# Microsoft) is not a cohort. Cohorts are per tenant (one tenant never blocks
# another). DNS lookups are cached and fail OPEN.

LIVE_WINDOW_DAYS = 14
_DNS_TTL_SECONDS = 3600
_DNS_FAILURE_TTL_SECONDS = 300
_ESP_SMTP_HOSTS = {
    h.lower() for profile in ISP_PROFILES.values() for h in profile.get("smtp_hosts", [])
} | {"smtp-mail.outlook.com", "smtp.mail.yahoo.com"}
_ESP_PROVIDERS = {EmailProvider.MICROSOFT_365, EmailProvider.GMAIL}

_dns_cache: dict[str, tuple[Optional[str], float]] = {}
_dns_lock = threading.Lock()


def _dns_lookup(host: str) -> str:
    """Resolve ``host`` to one IPv4 address (patched in tests)."""
    return socket.gethostbyname(host)


def clear_dns_cache() -> None:
    with _dns_lock:
        _dns_cache.clear()


def resolve_sending_ip(host: str) -> Optional[str]:
    """Cached host -> IP. None when resolution fails (callers fail open)."""
    host = (host or "").strip().lower()
    if not host:
        return None
    now = time.monotonic()
    with _dns_lock:
        hit = _dns_cache.get(host)
        if hit and hit[1] > now:
            return hit[0]
    try:
        ip: Optional[str] = _dns_lookup(host)
        ttl = _DNS_TTL_SECONDS
    except (OSError, UnicodeError, ValueError) as exc:
        logger.warning("cohort_dns_resolution_failed", host=host, error=str(exc))
        ip, ttl = None, _DNS_FAILURE_TTL_SECONDS
    with _dns_lock:
        _dns_cache[host] = (ip, now + ttl)
    return ip


def _sending_ip(dedicated_ip, provider, smtp_host) -> Optional[str]:
    if dedicated_ip:
        return str(dedicated_ip).strip() or None
    if provider in _ESP_PROVIDERS:
        return None
    host = (smtp_host or "").strip().lower()
    if not host or host in _ESP_SMTP_HOSTS:
        return None
    return resolve_sending_ip(host)


def mailbox_sending_ip(mailbox: SenderMailbox) -> Optional[str]:
    """The outbound IP a mailbox's domain is judged by, or None (no cohort / unknown)."""
    return _sending_ip(mailbox.dedicated_ip, mailbox.provider, mailbox.smtp_host)


def _email_domain(email: Optional[str]) -> str:
    return (email or "").rsplit("@", 1)[-1].strip().lower()


def max_live_domains_per_ip() -> int:
    return int(getattr(settings, "MAX_LIVE_DOMAINS_PER_IP", 1) or 0)


def cohort_blocked_ids(
    db: Session, mailboxes: list[SenderMailbox], now: Optional[datetime] = None
) -> set[int]:
    """Ids of candidate mailboxes blocked because their IP cohort has no free live slot.

    One query loads every live (tenant, domain, host) for the candidates' tenants.
    Free slots go to not-yet-live domains in alphabetical order, so a single
    selection can never admit more than the cap. A cap <= 0 disables the check.
    """
    cap = max_live_domains_per_ip()
    if cap <= 0 or not mailboxes:
        return set()
    candidates = [(mb, mailbox_sending_ip(mb)) for mb in mailboxes]
    candidates = [(mb, ip) for mb, ip in candidates if ip]
    if not candidates:
        return set()

    now = now or datetime.utcnow()
    cutoff = now - timedelta(days=LIVE_WINDOW_DAYS)
    tenant_ids = {mb.tenant_id for mb, _ in candidates}
    live_rows = (
        db.query(
            SenderMailbox.tenant_id,
            SenderMailbox.email,
            SenderMailbox.smtp_host,
            SenderMailbox.dedicated_ip,
            SenderMailbox.provider,
        )
        .join(OutreachEvent, OutreachEvent.sender_mailbox_id == SenderMailbox.mailbox_id)
        .filter(
            SenderMailbox.tenant_id.in_(tenant_ids),
            OutreachEvent.sent_at >= cutoff,
            *_real_outreach_filters(),
        )
        .distinct()
        .all()
    )
    live: dict[tuple, set[str]] = defaultdict(set)
    for tenant_id, email, smtp_host, dedicated_ip, provider in live_rows:
        ip = _sending_ip(dedicated_ip, provider, smtp_host)
        if ip:
            live[(tenant_id, ip)].add(_email_domain(email))

    blocked: set[int] = set()
    candidates.sort(key=lambda pair: (_email_domain(pair[0].email), pair[0].mailbox_id))
    for mb, ip in candidates:
        key = (mb.tenant_id, ip)
        domain = _email_domain(mb.email)
        if domain in live[key]:
            continue
        if len(live[key]) < cap:
            live[key].add(domain)  # admit this domain; later candidates see the slot taken
            continue
        blocked.add(mb.mailbox_id)
    if blocked:
        logger.info("cohort_cap_blocked_mailboxes", count=len(blocked), cap=cap)
    return blocked


# ---------------------------------------------------------------------------
# Combined outreach caps (D2 ramp + D3 cohort) for any selection query
# ---------------------------------------------------------------------------


def outreach_blocked_ids(
    db: Session, mailboxes: list[SenderMailbox], now: Optional[datetime] = None
) -> set[int]:
    """Candidates that hit their ramped daily cap or whose IP cohort is full."""
    if not mailboxes:
        return set()
    now = now or datetime.utcnow()
    firsts = first_outreach_dates(db, [mb.mailbox_id for mb in mailboxes])
    ramp_blocked = {
        mb.mailbox_id
        for mb in mailboxes
        if (mb.emails_sent_today or 0)
        >= effective_daily_limit(mb, firsts.get(mb.mailbox_id), now.date())
    }
    remaining = [mb for mb in mailboxes if mb.mailbox_id not in ramp_blocked]
    return ramp_blocked | cohort_blocked_ids(db, remaining, now)


def apply_outreach_caps(db: Session, query: Query) -> Query:
    """Narrow a mailbox selection query by the ramp and cohort caps.

    Loads the (already filtered) candidates once, then excludes blocked ids, so
    callers keep using ``.order_by(...).first()`` on the returned query.
    """
    blocked = outreach_blocked_ids(db, query.all())
    if blocked:
        query = query.filter(SenderMailbox.mailbox_id.notin_(blocked))
    return query


def calculate_engagement_rate(db: Session, mailbox_id: int, days: int = 7) -> float:
    """Calculate the engagement rate for a mailbox over a recent time window.

    Engagement rate = (events with reply_detected_at IS NOT NULL) / (total SENT events)
    for the given mailbox over the last `days` days.

    Args:
        db: SQLAlchemy database session.
        mailbox_id: The mailbox to evaluate.
        days: Number of days to look back. Defaults to 7.

    Returns:
        Float between 0.0 and 1.0 representing the engagement rate.
        Returns 0.0 if no sent events exist in the window.
    """
    cutoff = datetime.utcnow() - timedelta(days=days)

    total_sent = (
        db.query(sa_func.count(OutreachEvent.event_id))
        .filter(
            OutreachEvent.sender_mailbox_id == mailbox_id,
            OutreachEvent.status == OutreachStatus.SENT,
            OutreachEvent.sent_at >= cutoff,
        )
        .scalar()
    ) or 0

    if total_sent == 0:
        return 0.0

    engaged_count = (
        db.query(sa_func.count(OutreachEvent.event_id))
        .filter(
            OutreachEvent.sender_mailbox_id == mailbox_id,
            OutreachEvent.status == OutreachStatus.SENT,
            OutreachEvent.sent_at >= cutoff,
            OutreachEvent.reply_detected_at.isnot(None),
        )
        .scalar()
    ) or 0

    return round(engaged_count / total_sent, 4)


def calculate_mailbox_score(mailbox: SenderMailbox, engagement_rate: Optional[float] = None) -> float:
    """Compute a weighted score for a mailbox based on health, quota, warmup age, deliverability,
    and optionally engagement rate.

    Score ranges from 0.0 (worst) to 1.0 (best).

    Components:
        - health (40%): DNS score, bounce rate, complaint count
        - quota (30% without engagement, 20% with): remaining daily capacity as a fraction
        - warmup_age (15%): days warmed up, capped at maturity threshold
        - deliverability (15%): inverse of bounce rate
        - engagement (10%, only when provided): reply/open rate from recent sends

    Args:
        mailbox: The SenderMailbox instance to score.
        engagement_rate: Optional engagement rate (0.0-1.0). When provided, adds
            a 5th scoring component (10% weight) and reduces quota weight from 30% to 20%.
            When None, uses the original 4-component weights.

    Returns:
        A float score between 0.0 and 1.0.
    """
    total_sent = max(mailbox.total_emails_sent, 1)
    bounce_rate = mailbox.bounce_count / total_sent

    # --- Health component (0.4) ---
    dns_normalized = (mailbox.dns_score or 0) / 100.0
    bounce_penalty = 1.0 - min(bounce_rate * 5, 1.0)  # 20% bounce rate => zero score
    complaint_penalty = 1.0 - min((mailbox.complaint_count or 0) / 10.0, 1.0)
    health_component = (dns_normalized * 0.5 + bounce_penalty * 0.3 + complaint_penalty * 0.2)

    # --- Quota component (weight depends on engagement availability) ---
    daily_limit = max(mailbox.daily_send_limit, 1)
    remaining_quota = max(daily_limit - mailbox.emails_sent_today, 0)
    quota_component = remaining_quota / daily_limit

    # --- Warmup age component (0.15) ---
    warmup_days = mailbox.warmup_days_completed or 0
    warmup_age_component = min(warmup_days / WARMUP_MATURITY_DAYS, 1.0)

    # --- Deliverability component (0.15) ---
    deliverability_component = 1.0 - bounce_rate

    if engagement_rate is not None:
        # 5-component scoring: health 40%, quota 20%, warmup 15%, deliverability 15%, engagement 10%
        score = (
            WEIGHT_HEALTH * health_component
            + WEIGHT_QUOTA_WITH_ENGAGEMENT * quota_component
            + WEIGHT_WARMUP_AGE * warmup_age_component
            + WEIGHT_DELIVERABILITY * deliverability_component
            + WEIGHT_ENGAGEMENT * engagement_rate
        )
    else:
        # Original 4-component scoring
        score = (
            WEIGHT_HEALTH * health_component
            + WEIGHT_QUOTA * quota_component
            + WEIGHT_WARMUP_AGE * warmup_age_component
            + WEIGHT_DELIVERABILITY * deliverability_component
        )

    return round(score, 4)


def select_best_mailbox(
    campaign_mailbox_ids: list[int],
    db: Session,
    tenant_id: Optional[int] = None,
) -> Optional[SenderMailbox]:
    """Select the highest-scoring eligible mailbox for sending.

    Filters mailboxes by active status, warmup readiness, remaining quota,
    successful connection, and blacklist status. If campaign_mailbox_ids is
    provided and non-empty, only those mailboxes are considered.

    Args:
        campaign_mailbox_ids: List of mailbox IDs assigned to the campaign.
            If empty, all eligible mailboxes are considered.
        db: SQLAlchemy database session.
        tenant_id: The campaign's tenant. When given, only that tenant's mailboxes are
            eligible — an assigned id from another tenant is ignored, and the automated
            pool never crosses tenants.

    Returns:
        The highest-scoring SenderMailbox, or None if no mailbox is eligible.
    """
    query = db.query(SenderMailbox).filter(
        SenderMailbox.is_active == True,  # noqa: E712
        outreach_eligible_filter(),
        SenderMailbox.emails_sent_today < SenderMailbox.daily_send_limit,
        SenderMailbox.connection_status == "successful",
        SenderMailbox.is_blacklisted == False,  # noqa: E712
    )
    if tenant_id is not None:
        query = query.filter(SenderMailbox.tenant_id == tenant_id)

    if campaign_mailbox_ids:
        # Explicit (manual) assignment — send from exactly these mailboxes regardless of role.
        query = query.filter(SenderMailbox.mailbox_id.in_(campaign_mailbox_ids))
    else:
        # Automated pool — only mailboxes whose outreach role is flagged auto_outbound
        # (e.g. "RA"). Personal mailboxes (BDM/Recruiter/…) are manual-only.
        from app.db.models.outreach_role import OutreachRole
        query = query.join(
            OutreachRole, SenderMailbox.outreach_role_id == OutreachRole.role_id
        ).filter(OutreachRole.auto_outbound == True)  # noqa: E712

    eligible_mailboxes = query.all()
    # D2 ramp cap + D3 per-IP cohort cap (one batch of queries, not per mailbox).
    if eligible_mailboxes:
        blocked = outreach_blocked_ids(db, eligible_mailboxes)
        if blocked:
            eligible_mailboxes = [m for m in eligible_mailboxes if m.mailbox_id not in blocked]
            if not eligible_mailboxes:
                logger.warning(
                    "no_eligible_mailboxes_after_caps",
                    campaign_mailbox_ids=campaign_mailbox_ids,
                    capped=len(blocked),
                )
                return None

    if not eligible_mailboxes:
        # Diagnostic: on the auto path, count otherwise-eligible mailboxes excluded ONLY
        # by the role gate (no/non-auto_outbound role) so a stalled run is explainable.
        role_excluded = None
        if not campaign_mailbox_ids:
            role_excluded = (
                db.query(sa_func.count(SenderMailbox.mailbox_id))
                .filter(
                    SenderMailbox.is_active == True,  # noqa: E712
                    outreach_eligible_filter(),
                    SenderMailbox.emails_sent_today < SenderMailbox.daily_send_limit,
                    SenderMailbox.connection_status == "successful",
                    SenderMailbox.is_blacklisted == False,  # noqa: E712
                )
                .scalar()
                or 0
            )
        logger.warning(
            "no_eligible_mailboxes",
            campaign_mailbox_ids=campaign_mailbox_ids,
            role_gate_excluded=role_excluded,
        )
        return None

    # Calculate engagement rate for each eligible mailbox and include in scoring
    scored = []
    for mailbox in eligible_mailboxes:
        engagement_rate = calculate_engagement_rate(db, mailbox.mailbox_id)
        score = calculate_mailbox_score(mailbox, engagement_rate=engagement_rate)
        scored.append((mailbox, score, engagement_rate))

    scored.sort(key=lambda pair: pair[1], reverse=True)

    best_mailbox, best_score, best_engagement = scored[0]
    logger.info(
        "mailbox_selected",
        mailbox_id=best_mailbox.mailbox_id,
        email=best_mailbox.email,
        score=best_score,
        engagement_rate=best_engagement,
        eligible_count=len(eligible_mailboxes),
    )

    return best_mailbox
