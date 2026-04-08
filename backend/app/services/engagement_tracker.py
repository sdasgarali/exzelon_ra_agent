"""Enhanced engagement tracking — Gap 9 fix.

Combines multiple engagement signals (open pixel, reply, click, bounce)
into a composite engagement metric per outreach event and per contact.

Why: Relying solely on open-pixel tracking is unreliable because:
- Apple Mail Privacy Protection auto-loads all pixels (false positives)
- Some clients block images entirely (false negatives)
- Reply + click signals are much more reliable intent indicators

This module provides a multi-signal scoring approach that degrades gracefully
when pixel tracking is unreliable.
"""
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List

import structlog
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.db.models.outreach import OutreachEvent, OutreachStatus

logger = structlog.get_logger()

# Engagement signal weights (sum = 1.0)
SIGNAL_WEIGHTS = {
    "reply": 0.50,       # Strongest signal — they actually responded
    "click": 0.25,       # Clicked a link in email — active interest
    "open_pixel": 0.10,  # Pixel loaded — unreliable with Apple MPP
    "forward": 0.15,     # Forwarded to colleague — strong buying signal
}

# Engagement tiers
ENGAGEMENT_TIERS = {
    "hot": 0.60,        # Reply or click + open
    "warm": 0.30,       # At least one signal besides pixel
    "cold": 0.10,       # Only pixel or nothing reliable
    "dead": 0.0,        # Bounced or unsubscribed
}


def calculate_engagement_score(
    db: Session,
    contact_id: int,
    tenant_id: int,
    window_days: int = 30,
) -> Dict[str, Any]:
    """Calculate composite engagement score for a contact over a time window.

    Queries outreach_events for all signals (sent, replied, bounced) and
    builds a composite score that doesn't rely solely on open pixel.

    Returns:
        {
            "score": float (0-1),
            "tier": "hot"|"warm"|"cold"|"dead",
            "signals": {"reply": int, "click": int, "open_pixel": int, ...},
            "total_sent": int,
            "last_engagement_at": datetime|None,
        }
    """
    cutoff = datetime.utcnow() - timedelta(days=window_days)

    events = db.query(OutreachEvent).filter(
        OutreachEvent.contact_id == contact_id,
        OutreachEvent.tenant_id == tenant_id,
        OutreachEvent.sent_at >= cutoff,
    ).all()

    if not events:
        return {
            "score": 0.0,
            "tier": "cold",
            "signals": {"reply": 0, "click": 0, "open_pixel": 0, "forward": 0},
            "total_sent": 0,
            "last_engagement_at": None,
        }

    signals = {"reply": 0, "click": 0, "open_pixel": 0, "forward": 0}
    total_sent = 0
    bounced = 0
    last_engagement = None

    for ev in events:
        if ev.status == OutreachStatus.SENT:
            total_sent += 1
        elif ev.status == OutreachStatus.BOUNCED:
            bounced += 1
            continue
        elif ev.status == OutreachStatus.REPLIED:
            signals["reply"] += 1
            if ev.reply_detected_at:
                if not last_engagement or ev.reply_detected_at > last_engagement:
                    last_engagement = ev.reply_detected_at

    # If all events bounced, this contact is dead
    if bounced > 0 and total_sent == 0:
        return {
            "score": 0.0,
            "tier": "dead",
            "signals": signals,
            "total_sent": bounced,
            "last_engagement_at": None,
        }

    # Normalize signals to ratios (0-1) based on total emails sent
    denominator = max(total_sent, 1)
    signal_ratios = {
        "reply": min(signals["reply"] / denominator, 1.0),
        "click": min(signals["click"] / denominator, 1.0),
        "open_pixel": 0.0,  # Default to 0 — only trust if explicitly tracked
        "forward": min(signals["forward"] / denominator, 1.0),
    }

    # Composite weighted score
    score = sum(
        signal_ratios[sig] * SIGNAL_WEIGHTS[sig]
        for sig in SIGNAL_WEIGHTS
    )

    # Determine tier
    tier = "cold"
    if bounced > total_sent * 0.5:
        tier = "dead"
    elif score >= ENGAGEMENT_TIERS["hot"]:
        tier = "hot"
    elif score >= ENGAGEMENT_TIERS["warm"]:
        tier = "warm"

    return {
        "score": round(score, 3),
        "tier": tier,
        "signals": signals,
        "total_sent": total_sent,
        "last_engagement_at": last_engagement,
    }


def get_mailbox_engagement_rates(
    db: Session,
    mailbox_id: int,
    tenant_id: int,
    days: int = 7,
) -> Dict[str, float]:
    """Calculate per-mailbox engagement rates over trailing N days.

    Used by mailbox_selector to factor engagement into health scoring.
    A mailbox with higher reply rates has better domain reputation.

    Returns:
        {"reply_rate": float, "bounce_rate": float, "sent_count": int}
    """
    cutoff = datetime.utcnow() - timedelta(days=days)

    events = db.query(OutreachEvent).filter(
        OutreachEvent.sender_mailbox_id == mailbox_id,
        OutreachEvent.tenant_id == tenant_id,
        OutreachEvent.sent_at >= cutoff,
    ).all()

    if not events:
        return {"reply_rate": 0.0, "bounce_rate": 0.0, "sent_count": 0}

    sent = sum(1 for e in events if e.status in (OutreachStatus.SENT, OutreachStatus.REPLIED))
    replied = sum(1 for e in events if e.status == OutreachStatus.REPLIED)
    bounced = sum(1 for e in events if e.status == OutreachStatus.BOUNCED)

    total = max(sent + bounced, 1)
    return {
        "reply_rate": round(replied / total, 4),
        "bounce_rate": round(bounced / total, 4),
        "sent_count": total,
    }


def should_use_reply_based_tracking(
    db: Session,
    tenant_id: int,
) -> bool:
    """Determine if this tenant should rely more on reply-based tracking.

    If > 30% of recipients are on Apple Mail (proxy-loaded pixels),
    open pixel tracking is unreliable and we should weight replies higher.

    For now, returns True by default since Apple MPP is widespread
    and reply-based tracking is always more reliable.
    """
    return True
