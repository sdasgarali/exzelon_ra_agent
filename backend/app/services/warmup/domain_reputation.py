"""Domain Reputation Tracker - DNS+blacklist proxy score + ISP-specific warmup profiles."""
from typing import Dict, Any

import structlog
from sqlalchemy.orm import Session

from app.db.models.sender_mailbox import SenderMailbox

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# ISP-specific warmup profiles
# ---------------------------------------------------------------------------

ISP_PROFILES: Dict[str, Dict[str, Any]] = {
    "gmail": {
        "name": "Gmail / Google Workspace",
        "domains": ["gmail.com", "googlemail.com"],
        "smtp_hosts": ["smtp.gmail.com", "smtp.google.com"],
        "strategy": "engagement",
        "description": (
            "Gmail prioritizes engagement signals (opens, replies, clicks). "
            "Focus on high reply-rate warmup with AI-generated conversational content."
        ),
        "recommended_daily_ramp": [2, 4, 6, 8, 12, 16, 20, 25, 30],
        "recommended_reply_rate": 0.5,
        "key_factors": ["reply_rate", "open_rate", "authentication", "content_quality"],
    },
    "outlook": {
        "name": "Microsoft Outlook / O365",
        "domains": ["outlook.com", "hotmail.com", "live.com", "msn.com"],
        "smtp_hosts": ["smtp.office365.com", "outlook.office365.com"],
        "strategy": "authentication",
        "description": (
            "Outlook weights authentication (SPF/DKIM/DMARC) and sender history heavily. "
            "Ensure perfect DNS before ramping volume."
        ),
        "recommended_daily_ramp": [2, 4, 8, 12, 16, 20, 25, 30, 35, 40],
        "recommended_reply_rate": 0.4,
        "key_factors": ["spf_pass", "dkim_pass", "dmarc_pass", "sender_history"],
    },
    "yahoo": {
        "name": "Yahoo / AOL",
        "domains": ["yahoo.com", "aol.com", "ymail.com"],
        "smtp_hosts": [],
        "strategy": "consistency",
        "description": (
            "Yahoo rewards volume consistency. Avoid sudden spikes. "
            "Steady daily sends with minimal variance."
        ),
        "recommended_daily_ramp": [2, 3, 5, 7, 10, 14, 18, 22, 26, 30],
        "recommended_reply_rate": 0.3,
        "key_factors": ["volume_consistency", "low_bounce_rate", "spam_trap_avoidance"],
    },
    "other": {
        "name": "General / Corporate",
        "domains": [],
        "smtp_hosts": [],
        "strategy": "balanced",
        "description": "Balanced approach with moderate ramp and focus on content quality.",
        "recommended_daily_ramp": [2, 5, 8, 12, 16, 20, 25, 30],
        "recommended_reply_rate": 0.3,
        "key_factors": ["authentication", "content_quality", "bounce_rate"],
    },
}


def detect_isp(email_or_host: str) -> str:
    """Detect the ISP from an email address or SMTP host.

    Args:
        email_or_host: An email address (user@domain.com) or SMTP hostname.

    Returns:
        ISP key: "gmail", "outlook", "yahoo", or "other".
    """
    value = (email_or_host or "").lower().strip()

    # Extract domain from email if it contains @
    if "@" in value:
        value = value.split("@")[1]

    # Check each ISP profile's domains and smtp_hosts
    for isp_key, profile in ISP_PROFILES.items():
        if isp_key == "other":
            continue
        if value in profile["domains"]:
            return isp_key
        if value in profile["smtp_hosts"]:
            return isp_key

    return "other"


def get_warmup_recommendation(mailbox_id: int, db: Session) -> Dict[str, Any]:
    """Get ISP-specific warmup recommendation for a mailbox.

    Looks up the mailbox, detects its ISP, and returns the appropriate
    warmup profile along with today's recommended daily send volume.

    Args:
        mailbox_id: Primary key of the SenderMailbox.
        db: SQLAlchemy Session.

    Returns:
        Dict with: isp, profile (full ISP profile dict), warmup_day,
        recommended_daily_volume, strategy, key_factors.
        Returns error dict if mailbox not found.
    """
    mailbox = db.query(SenderMailbox).filter(
        SenderMailbox.mailbox_id == mailbox_id
    ).first()

    if not mailbox:
        return {"error": "Mailbox not found"}

    # Detect ISP from email domain or SMTP host
    isp_key = detect_isp(mailbox.email)

    # Also try SMTP host — it may give a more specific match
    if isp_key == "other" and mailbox.smtp_host:
        isp_key = detect_isp(mailbox.smtp_host)

    profile = ISP_PROFILES[isp_key]
    warmup_day = mailbox.warmup_days_completed or 0
    ramp = profile["recommended_daily_ramp"]

    # Determine today's recommended volume based on warmup day
    if warmup_day < len(ramp):
        recommended_volume = ramp[warmup_day]
    else:
        # Past the ramp schedule — use the final (max) value
        recommended_volume = ramp[-1] if ramp else 30

    logger.info(
        "warmup_recommendation",
        mailbox_id=mailbox_id,
        email=mailbox.email,
        isp=isp_key,
        warmup_day=warmup_day,
        recommended_volume=recommended_volume,
    )

    return {
        "mailbox_id": mailbox_id,
        "email": mailbox.email,
        "isp": isp_key,
        "isp_name": profile["name"],
        "strategy": profile["strategy"],
        "description": profile["description"],
        "warmup_day": warmup_day,
        "recommended_daily_volume": recommended_volume,
        "recommended_reply_rate": profile["recommended_reply_rate"],
        "key_factors": profile["key_factors"],
        "full_ramp_schedule": ramp,
    }


# ---------------------------------------------------------------------------
# Existing domain reputation functions (unchanged)
# ---------------------------------------------------------------------------

def calculate_domain_score(dns_score: int, is_blacklisted: bool, bounce_rate: float = 0) -> int:
    """Calculate composite domain reputation score from DNS, blacklist, and bounce data."""
    score = dns_score
    if is_blacklisted:
        score = max(0, score - 40)
    if bounce_rate > 5:
        score = max(0, score - 20)
    elif bounce_rate > 2:
        score = max(0, score - 10)
    return min(100, score)


def get_domain_reputation(mailbox_id: int, db: Session) -> Dict[str, Any]:
    """Get domain reputation report for a mailbox."""
    mailbox = db.query(SenderMailbox).filter(SenderMailbox.mailbox_id == mailbox_id).first()
    if not mailbox:
        return {"error": "Mailbox not found"}

    domain = mailbox.email.split("@")[1]
    total_sent = mailbox.total_emails_sent or 0
    bounce_rate = (mailbox.bounce_count / total_sent * 100) if total_sent > 0 else 0

    score = calculate_domain_score(
        dns_score=mailbox.dns_score or 0,
        is_blacklisted=mailbox.is_blacklisted or False,
        bounce_rate=bounce_rate,
    )

    return {
        "mailbox_id": mailbox_id,
        "domain": domain,
        "reputation_score": score,
        "dns_score": mailbox.dns_score or 0,
        "is_blacklisted": mailbox.is_blacklisted or False,
        "bounce_rate": round(bounce_rate, 2),
        "last_dns_check": str(mailbox.last_dns_check_at) if mailbox.last_dns_check_at else None,
        "last_blacklist_check": str(mailbox.last_blacklist_check_at) if mailbox.last_blacklist_check_at else None,
    }
