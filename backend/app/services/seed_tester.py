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


def check_seed_results(test_run_id: str, db: Session) -> Dict[str, Any]:
    """Check inbox placement via IMAP for unchecked seed test results.

    Connects to each seed account via IMAP, searches for the test email,
    and records whether it landed in inbox, spam, or was not delivered.
    """
    import imaplib

    results = db.query(SeedTestResult).filter(
        SeedTestResult.test_run_id == test_run_id,
        SeedTestResult.checked_at.is_(None),
    ).all()

    if not results:
        return {"test_run_id": test_run_id, "message": "No unchecked results", "total": 0}

    summary = {"total": len(results), "inbox": 0, "spam": 0, "not_delivered": 0, "error": 0}

    for result in results:
        seed_acct = db.query(SeedTestAccount).filter(
            SeedTestAccount.account_id == result.seed_account_id
        ).first()
        if not seed_acct or not seed_acct.imap_password:
            result.placement = "error"
            result.checked_at = datetime.utcnow()
            summary["error"] += 1
            continue

        # Resolve IMAP host — use explicit or infer from provider
        imap_host = seed_acct.imap_host
        if not imap_host:
            provider_hosts = {
                "gmail": "imap.gmail.com",
                "outlook": "outlook.office365.com",
                "yahoo": "imap.mail.yahoo.com",
            }
            imap_host = provider_hosts.get(seed_acct.provider, "")
        if not imap_host:
            result.placement = "error"
            result.checked_at = datetime.utcnow()
            summary["error"] += 1
            continue

        placement = "not_delivered"
        try:
            mail = imaplib.IMAP4_SSL(imap_host, seed_acct.imap_port or 993)
            mail.login(seed_acct.email, seed_acct.imap_password)

            # Check INBOX first
            mail.select("INBOX")
            _, data = mail.search(None, f'(SUBJECT "Inbox Placement Test [{test_run_id}]")')
            if data[0]:
                placement = "inbox"
            else:
                # Check Spam/Junk folders
                for folder in ["[Gmail]/Spam", "Junk", "Spam", "Junk E-mail"]:
                    try:
                        status, _ = mail.select(folder)
                        if status == "OK":
                            _, data = mail.search(None, f'(SUBJECT "Inbox Placement Test [{test_run_id}]")')
                            if data[0]:
                                placement = "spam"
                                break
                    except Exception:
                        continue

            mail.logout()
        except Exception as e:
            logger.warning("imap_check_failed", seed_email=seed_acct.email, error=str(e))
            placement = "error"

        result.placement = placement
        result.checked_at = datetime.utcnow()
        if result.created_at:
            result.latency_seconds = int((result.checked_at - result.created_at).total_seconds())
        summary[placement] = summary.get(placement, 0) + 1

    db.commit()

    inbox_rate = round(summary["inbox"] / summary["total"] * 100, 1) if summary["total"] > 0 else 0
    return {
        "test_run_id": test_run_id,
        **summary,
        "inbox_rate": inbox_rate,
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
