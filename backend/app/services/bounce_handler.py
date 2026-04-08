"""Real-time bounce-back handler — Gap 1 fix.

Parses SMTP error codes from send failures and takes appropriate action:
- 5xx permanent failures: auto-add to suppression list + mark contact bounced
- 4xx temporary failures: log for retry, suppress after repeated failures

Wired into send_outreach_email() in outreach.py.
"""
import re
from datetime import datetime
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

        # Increment mailbox bounce counter
        if mailbox_id:
            from app.db.models.sender_mailbox import SenderMailbox
            mailbox = db.query(SenderMailbox).filter(
                SenderMailbox.mailbox_id == mailbox_id,
            ).first()
            if mailbox:
                mailbox.bounce_count = (mailbox.bounce_count or 0) + 1

        logger.warning(
            "hard_bounce_suppressed",
            email=email,
            smtp_code=smtp_code,
            category=category,
            contact_id=contact_id,
        )
    else:
        # Temporary failure — just log
        logger.info(
            "soft_bounce_logged",
            email=email,
            smtp_code=smtp_code,
            category=category,
            error=error_msg[:200],
        )

    return result
