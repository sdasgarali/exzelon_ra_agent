"""Inbox placement seed testing service."""
import uuid
from datetime import datetime
from typing import Dict, Any
import structlog
from sqlalchemy.orm import Session

from app.db.models.seed_test import SeedTestAccount, SeedTestResult
from app.db.models.sender_mailbox import SenderMailbox

logger = structlog.get_logger()


def run_seed_test(mailbox_id: int, db: Session) -> Dict[str, Any]:
    """Send test emails to seed accounts and check inbox placement.

    This is a simplified implementation — full IMAP checking
    requires async polling (future enhancement).
    """
    mailbox = db.query(SenderMailbox).filter(
        SenderMailbox.mailbox_id == mailbox_id
    ).first()
    if not mailbox:
        return {"error": "Mailbox not found"}

    seed_accounts = db.query(SeedTestAccount).filter(
        SeedTestAccount.is_active == True,
        SeedTestAccount.is_archived == False,
    ).all()

    if not seed_accounts:
        return {"error": "No seed test accounts configured"}

    test_run_id = str(uuid.uuid4())[:8]
    results_created = 0

    for seed_acct in seed_accounts:
        # Create a pending result
        result = SeedTestResult(
            mailbox_id=mailbox_id,
            test_run_id=test_run_id,
            seed_account_id=seed_acct.account_id,
            placement=None,  # will be filled after IMAP check
            checked_at=None,
        )
        db.add(result)
        results_created += 1

        # Send test email
        try:
            from app.services.pipelines.outreach import send_outreach_email
            subject = f"Inbox Placement Test [{test_run_id}]"
            body = f"<p>This is an automated inbox placement test.</p><p>Test ID: {test_run_id}</p>"
            send_outreach_email(
                sender_mailbox=mailbox,
                to_email=seed_acct.email,
                subject=subject,
                body_html=body,
                body_text=f"Inbox placement test. ID: {test_run_id}",
            )
        except Exception as e:
            logger.error("Seed test send failed", seed_email=seed_acct.email, error=str(e))
            result.placement = "send_failed"
            result.checked_at = datetime.utcnow()

    db.commit()

    return {
        "test_run_id": test_run_id,
        "mailbox_id": mailbox_id,
        "seed_accounts_tested": results_created,
        "message": "Test emails sent. Check results in a few minutes.",
    }


def get_test_results(test_run_id: str, db: Session) -> list:
    """Get results for a specific test run."""
    results = db.query(SeedTestResult).filter(
        SeedTestResult.test_run_id == test_run_id,
    ).all()

    return [
        {
            "result_id": r.result_id,
            "seed_account_id": r.seed_account_id,
            "placement": r.placement,
            "checked_at": r.checked_at.isoformat() if r.checked_at else None,
            "latency_seconds": r.latency_seconds,
        }
        for r in results
    ]
