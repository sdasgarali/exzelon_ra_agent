"""Health-aware mailbox selection service.

Replaces simple round-robin mailbox selection with weighted scoring
based on DNS health, remaining quota, warmup maturity, and deliverability.
"""

from typing import Optional

import structlog
from sqlalchemy.orm import Session

from app.db.models.sender_mailbox import SenderMailbox, WarmupStatus

logger = structlog.get_logger(__name__)

# Scoring weights
WEIGHT_HEALTH = 0.40
WEIGHT_QUOTA = 0.30
WEIGHT_WARMUP_AGE = 0.15
WEIGHT_DELIVERABILITY = 0.15

# Warmup maturity threshold in days
WARMUP_MATURITY_DAYS = 30

# Eligible warmup statuses for sending
ELIGIBLE_WARMUP_STATUSES = [WarmupStatus.COLD_READY, WarmupStatus.ACTIVE]


def calculate_mailbox_score(mailbox: SenderMailbox) -> float:
    """Compute a weighted score for a mailbox based on health, quota, warmup age, and deliverability.

    Score ranges from 0.0 (worst) to 1.0 (best).

    Components:
        - health (40%): DNS score, bounce rate, complaint count
        - quota (30%): remaining daily capacity as a fraction
        - warmup_age (15%): days warmed up, capped at maturity threshold
        - deliverability (15%): inverse of bounce rate

    Args:
        mailbox: The SenderMailbox instance to score.

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

    # --- Quota component (0.3) ---
    daily_limit = max(mailbox.daily_send_limit, 1)
    remaining_quota = max(daily_limit - mailbox.emails_sent_today, 0)
    quota_component = remaining_quota / daily_limit

    # --- Warmup age component (0.15) ---
    warmup_days = mailbox.warmup_days_completed or 0
    warmup_age_component = min(warmup_days / WARMUP_MATURITY_DAYS, 1.0)

    # --- Deliverability component (0.15) ---
    deliverability_component = 1.0 - bounce_rate

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
        query = query.filter(SenderMailbox.mailbox_id.in_(campaign_mailbox_ids))

    eligible_mailboxes = query.all()

    if not eligible_mailboxes:
        logger.warning(
            "no_eligible_mailboxes",
            campaign_mailbox_ids=campaign_mailbox_ids,
        )
        return None

    scored = [(mailbox, calculate_mailbox_score(mailbox)) for mailbox in eligible_mailboxes]
    scored.sort(key=lambda pair: pair[1], reverse=True)

    best_mailbox, best_score = scored[0]
    logger.info(
        "mailbox_selected",
        mailbox_id=best_mailbox.mailbox_id,
        email=best_mailbox.email,
        score=best_score,
        eligible_count=len(eligible_mailboxes),
    )

    return best_mailbox
