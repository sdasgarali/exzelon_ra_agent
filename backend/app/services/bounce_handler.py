"""Real-time bounce-back handler — Gap 1 fix.

Parses SMTP error codes from send failures and takes appropriate action:
- 5xx permanent failures: auto-add to suppression list + mark contact bounced
- 4xx temporary failures: log for retry, suppress after repeated failures

Wired into send_outreach_email() in outreach.py.
"""
import re
from typing import Optional, Tuple

import structlog
from sqlalchemy.orm import Session

from app.db.models.contact import ContactDetails, OutreachStatus as ContactOutreachStatus
from app.db.models.suppression import SuppressionList

logger = structlog.get_logger()

# SMTP error code ranges
PERMANENT_FAILURE_CODES = range(500, 600)  # 5xx = permanent
TEMPORARY_FAILURE_CODES = range(400, 500)  # 4xx = temporary

# Max temporary failures before treating as permanent
MAX_TEMP_FAILURES = 3

# Common bounce reason patterns
BOUNCE_PATTERNS = {
    "mailbox_full": re.compile(r"(mailbox full|over quota|storage|exceeded)", re.I),
    "user_unknown": re.compile(r"(user unknown|no such user|does not exist|invalid recipient|unknown user|recipient rejected)", re.I),
    "domain_not_found": re.compile(r"(domain not found|no mx|host not found|name not resolved)", re.I),
    "blocked": re.compile(r"(blocked|blacklist|denied|rejected|spam)", re.I),
    "policy": re.compile(r"(policy|compliance|authentication|dmarc|spf fail)", re.I),
}


def classify_smtp_error(error_msg: str) -> Tuple[str, str, bool]:
    """Classify an SMTP error message into a bounce category.

    Returns:
        (smtp_code, bounce_category, is_permanent)
    """
    if not error_msg:
        return "unknown", "unknown", False

    # Extract SMTP code from error string
    code_match = re.search(r"\b([45]\d{2})\b", error_msg)
    smtp_code = code_match.group(1) if code_match else "unknown"

    # Determine if permanent
    is_permanent = False
    if smtp_code != "unknown":
        code_int = int(smtp_code)
        is_permanent = code_int in PERMANENT_FAILURE_CODES

    # Classify bounce reason
    category = "other"
    for cat, pattern in BOUNCE_PATTERNS.items():
        if pattern.search(error_msg):
            category = cat
            break

    # user_unknown and domain_not_found are always permanent
    if category in ("user_unknown", "domain_not_found"):
        is_permanent = True

    return smtp_code, category, is_permanent


def handle_bounce(
    db: Session,
    email: str,
    error_msg: str,
    contact_id: Optional[int] = None,
    tenant_id: int = 1,
    mailbox_id: Optional[int] = None,
) -> dict:
    """Process a bounce event and take appropriate action.

    For permanent bounces (5xx, user_unknown, domain_not_found):
    - Add email to suppression list
    - Mark contact as bounced if contact_id provided
    - Increment mailbox bounce_count

    For temporary bounces (4xx):
    - Log the failure
    - Check if max retries exceeded → treat as permanent

    Returns dict with action taken.
    """
    smtp_code, category, is_permanent = classify_smtp_error(error_msg)

    result = {
        "email": email,
        "smtp_code": smtp_code,
        "category": category,
        "is_permanent": is_permanent,
        "action": "logged",
    }

    if is_permanent:
        result["action"] = "suppressed"

        # Add to suppression list (if not already there)
        existing = db.query(SuppressionList).filter(
            SuppressionList.email == email.lower(),
        ).first()
        if not existing:
            suppression = SuppressionList(
                tenant_id=tenant_id,
                email=email.lower(),
                reason=f"hard_bounce: {category} ({smtp_code})",
            )
            db.add(suppression)

        # Mark contact as bounced
        if contact_id:
            contact = db.query(ContactDetails).filter(
                ContactDetails.contact_id == contact_id,
            ).first()
            if contact:
                contact.outreach_status = ContactOutreachStatus.INACTIVE
                contact.validation_status = "invalid"

        # Increment mailbox bounce counter (+ auto-pause on high bounce rate)
        if mailbox_id:
            _bump_mailbox_bounce(db, mailbox_id)

        logger.warning(
            "hard_bounce_suppressed",
            email=email,
            smtp_code=smtp_code,
            category=category,
            contact_id=contact_id,
        )
    else:
        # Temporary (4xx) failure — count it; escalate to a permanent suppression
        # once the same address soft-bounces MAX_TEMP_FAILURES times (ELR-015).
        count = _record_soft_bounce(db, tenant_id, email)
        if count >= MAX_TEMP_FAILURES:
            result["action"] = "suppressed_after_max_soft"
            existing = db.query(SuppressionList).filter(
                SuppressionList.email == email.lower(),
            ).first()
            if not existing:
                db.add(SuppressionList(
                    tenant_id=tenant_id,
                    email=email.lower(),
                    reason=f"soft_bounce_max ({count}x {smtp_code})",
                ))
            if contact_id:
                contact = db.query(ContactDetails).filter(
                    ContactDetails.contact_id == contact_id,
                ).first()
                if contact:
                    contact.outreach_status = ContactOutreachStatus.INACTIVE
            if mailbox_id:
                _bump_mailbox_bounce(db, mailbox_id)
            logger.warning("soft_bounce_escalated_to_suppression",
                           email=email, count=count, smtp_code=smtp_code)
        else:
            logger.info(
                "soft_bounce_logged",
                email=email,
                smtp_code=smtp_code,
                category=category,
                count=count,
                error=error_msg[:200],
            )

    return result


def _record_soft_bounce(db: Session, tenant_id: int, email: str) -> int:
    """Increment and return the soft-bounce count for (tenant, email)."""
    from app.db.models.soft_bounce import SoftBounceTracker
    email_lc = (email or "").lower()
    row = db.query(SoftBounceTracker).filter(
        SoftBounceTracker.tenant_id == tenant_id,
        SoftBounceTracker.email == email_lc,
    ).first()
    if row is None:
        row = SoftBounceTracker(tenant_id=tenant_id, email=email_lc, count=1)
        db.add(row)
        db.flush()
    else:
        row.count += 1
        db.flush()
    return row.count


# A mailbox whose bounce rate exceeds this fraction is auto-paused (ELR-015).
BOUNCE_RATE_AUTO_PAUSE_THRESHOLD = 0.05
MIN_SENDS_FOR_BOUNCE_RATE = 20


def _bump_mailbox_bounce(db: Session, mailbox_id: int) -> None:
    """Increment a mailbox's bounce count and auto-pause it if the bounce rate is
    too high (over a minimum send volume)."""
    from app.db.models.sender_mailbox import SenderMailbox
    mailbox = db.query(SenderMailbox).filter(
        SenderMailbox.mailbox_id == mailbox_id,
    ).first()
    if not mailbox:
        return
    mailbox.bounce_count = (mailbox.bounce_count or 0) + 1
    sent = mailbox.total_emails_sent or 0
    if sent >= MIN_SENDS_FOR_BOUNCE_RATE:
        rate = mailbox.bounce_count / sent
        if rate > BOUNCE_RATE_AUTO_PAUSE_THRESHOLD and mailbox.is_active:
            mailbox.is_active = False
            logger.warning("mailbox_auto_paused_high_bounce_rate",
                           mailbox_id=mailbox_id, bounce_rate=round(rate, 4),
                           bounce_count=mailbox.bounce_count, sent=sent)
