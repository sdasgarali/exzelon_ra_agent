"""Domain Reputation Tracker - DNS+blacklist proxy score."""
from datetime import datetime
from typing import Dict, Any
from sqlalchemy.orm import Session

from app.db.models.sender_mailbox import SenderMailbox


def calculate_domain_score(dns_score: int, is_blacklisted: bool, bounce_rate: float = 0) -> int:
    score = dns_score
    if is_blacklisted:
        score = max(0, score - 40)
    if bounce_rate > 5:
        score = max(0, score - 20)
    elif bounce_rate > 2:
        score = max(0, score - 10)
    return min(100, score)


def get_domain_reputation(mailbox_id: int, db: Session) -> Dict[str, Any]:
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
