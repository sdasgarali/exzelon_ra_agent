"""Inbox Placement Testing - seed email testing."""
import smtplib
import imaplib
import json
from email.mime.text import MIMEText
from datetime import datetime
from typing import Dict, Any
from sqlalchemy.orm import Session

from app.db.models.sender_mailbox import SenderMailbox
from app.db.models.settings import Settings


def _get_setting(db: Session, key: str, default=None):
    setting = db.query(Settings).filter(Settings.key == key).first()
    if setting and setting.value_json:
        try:
            return json.loads(setting.value_json)
        except Exception:
            pass
    return default


def send_seed_email(mailbox: SenderMailbox, seed_email: str, subject: str = None) -> Dict[str, Any]:
    try:
        if not subject:
            subject = f"Inbox placement test - {datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        body = "This is an automated inbox placement test email."
        msg = MIMEText(body)
        msg["From"] = mailbox.email
        msg["To"] = seed_email
        msg["Subject"] = subject

        smtp_host = mailbox.smtp_host or "smtp.office365.com"
        server = smtplib.SMTP(smtp_host, mailbox.smtp_port or 587, timeout=30)
        server.starttls()
        from app.services.oauth_helper import smtp_authenticate
        from app.db.base import SessionLocal
        _auth_db = SessionLocal()
        try:
            smtp_authenticate(server, mailbox.email, mailbox, _auth_db)
        finally:
            _auth_db.close()
        server.sendmail(mailbox.email, seed_email, msg.as_string())
        server.quit()
        return {"success": True, "subject": subject}
    except Exception as e:
        return {"success": False, "error": str(e)}


def run_placement_test(mailbox_id: int, db: Session) -> Dict[str, Any]:
    mailbox = db.query(SenderMailbox).filter(SenderMailbox.mailbox_id == mailbox_id).first()
    if not mailbox:
        return {"error": "Mailbox not found"}

    seed_emails = _get_setting(db, "warmup_seed_emails_json", [])
    if isinstance(seed_emails, str):
        try:
            seed_emails = json.loads(seed_emails)
        except Exception:
            seed_emails = []

    if not seed_emails:
        return {"error": "No seed emails configured", "mailbox_id": mailbox_id}

    results = []
    for seed in seed_emails:
        email = seed if isinstance(seed, str) else seed.get("email", "")
        provider = seed.get("provider", "unknown") if isinstance(seed, dict) else "unknown"
        result = send_seed_email(mailbox, email)
        results.append({
            "seed_email": email,
            "provider": provider,
            "sent": result.get("success", False),
            "error": result.get("error"),
            "placement": "pending",
        })

    return {"mailbox_id": mailbox_id, "tests_sent": len(results), "results": results}
