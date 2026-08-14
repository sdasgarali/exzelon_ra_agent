"""Health-aware mailbox selection service.

Replaces simple round-robin mailbox selection with weighted scoring
based on DNS health, remaining quota, warmup maturity, deliverability,
and optionally engagement rate.
"""

from datetime import datetime, timedelta
from typing import Optional

import structlog
from sqlalchemy import func as sa_func
from sqlalchemy.orm import Session

from app.db.models.outreach import OutreachEvent, OutreachStatus
from app.db.models.sender_mailbox import SenderMailbox, WarmupStatus

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
) -> Optional[SenderMailbox]:
    """Select the highest-scoring eligible mailbox for sending.

    Filters mailboxes by active status, warmup readiness, remaining quota,
    successful connection, and blacklist status. If campaign_mailbox_ids is
    provided and non-empty, only those mailboxes are considered.

    Args:
        campaign_mailbox_ids: List of mailbox IDs assigned to the campaign.
            If empty, all eligible mailboxes are considered.
        db: SQLAlchemy database session.

    Returns:
        The highest-scoring SenderMailbox, or None if no mailbox is eligible.
    """
    query = db.query(SenderMailbox).filter(
        SenderMailbox.is_active == True,  # noqa: E712
        SenderMailbox.warmup_status.in_(ELIGIBLE_WARMUP_STATUSES),
        SenderMailbox.emails_sent_today < SenderMailbox.daily_send_limit,
        SenderMailbox.connection_status == "successful",
        SenderMailbox.is_blacklisted == False,  # noqa: E712
    )

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

    if not eligible_mailboxes:
        # Diagnostic: on the auto path, count otherwise-eligible mailboxes excluded ONLY
        # by the role gate (no/non-auto_outbound role) so a stalled run is explainable.
        role_excluded = None
        if not campaign_mailbox_ids:
            role_excluded = (
                db.query(sa_func.count(SenderMailbox.mailbox_id))
                .filter(
                    SenderMailbox.is_active == True,  # noqa: E712
                    SenderMailbox.warmup_status.in_(ELIGIBLE_WARMUP_STATUSES),
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
