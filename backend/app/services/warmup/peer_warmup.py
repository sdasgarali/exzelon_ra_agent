"""Peer Warmup Email Service - mailboxes email each other to build ISP reputation."""
import random
import smtplib
import uuid
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import json
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from app.db.models.sender_mailbox import SenderMailbox, WarmupStatus
from app.db.models.warmup_email import WarmupEmail, WarmupEmailStatus
from app.db.models.settings import Settings
from app.services.warmup.tracking import inject_tracking


def _get_setting(db: Session, key: str, default=None):
    setting = db.query(Settings).filter(Settings.key == key).first()
    if setting and setting.value_json:
        try:
            return json.loads(setting.value_json)
        except Exception:
            pass
    return default


def get_peer_pairs(db: Session, mailbox: SenderMailbox) -> List[SenderMailbox]:
    peers = db.query(SenderMailbox).filter(
        and_(
            SenderMailbox.mailbox_id != mailbox.mailbox_id,
            SenderMailbox.warmup_status.in_([WarmupStatus.WARMING_UP, WarmupStatus.RECOVERING]),
            SenderMailbox.is_active == True,
            SenderMailbox.connection_status == "successful",
        )
    ).all()
    if not peers:
        return []
    max_per_pair = int(_get_setting(db, "warmup_peer_max_emails_per_pair", 3))
    random.shuffle(peers)
    return peers[:max_per_pair]


def send_warmup_email(sender_mailbox: SenderMailbox, receiver_email: str, subject: str, body_html: str, body_text: str) -> Dict[str, Any]:
    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = f"{sender_mailbox.display_name or sender_mailbox.email} <{sender_mailbox.email}>"
        msg["To"] = receiver_email
        msg["Subject"] = subject
        msg["Message-ID"] = f"<{uuid.uuid4()}@{sender_mailbox.email.split('@')[1]}>"

        msg.attach(MIMEText(body_text, "plain"))
        msg.attach(MIMEText(body_html, "html"))

        smtp_host = sender_mailbox.smtp_host or "smtp.office365.com"
        server = smtplib.SMTP(smtp_host, sender_mailbox.smtp_port or 587, timeout=30)
        server.starttls()
        from app.core.encryption import decrypt_field
        server.login(sender_mailbox.email, decrypt_field(sender_mailbox.password))
        server.sendmail(sender_mailbox.email, receiver_email, msg.as_string())
        server.quit()

        return {"success": True, "message_id": msg["Message-ID"]}
    except Exception as e:
        return {"success": False, "error": str(e)}


def run_peer_warmup_cycle(db: Session, mailbox_id: int = None) -> Dict[str, Any]:
    from app.services.warmup.content_generator import generate_warmup_subject, generate_warmup_body, generate_ai_warmup_content
    from app.services.warmup.smart_scheduler import should_skip_weekend

    if should_skip_weekend(db):
        return {"skipped": True, "reason": "Weekend - skipping warmup"}

    enabled = _get_setting(db, "warmup_peer_enabled", True)
    if not enabled:
        return {"skipped": True, "reason": "Peer warmup disabled"}

    query = db.query(SenderMailbox).filter(
        SenderMailbox.warmup_status.in_([WarmupStatus.WARMING_UP, WarmupStatus.RECOVERING]),
        SenderMailbox.is_active == True,
        SenderMailbox.connection_status == "successful",
    )
    if mailbox_id:
        query = query.filter(SenderMailbox.mailbox_id == mailbox_id)

    mailboxes = query.all()
    results = {"total": 0, "sent": 0, "failed": 0, "details": []}

    for mb in mailboxes:
        if mb.emails_sent_today >= mb.daily_send_limit:
            continue

        peers = get_peer_pairs(db, mb)
        for peer in peers:
            if mb.emails_sent_today >= mb.daily_send_limit:
                break

            sender_name = mb.display_name or mb.email.split("@")[0]
            receiver_name = peer.display_name or peer.email.split("@")[0]

            # Try AI content first, fallback to templates
            ai_content = generate_ai_warmup_content(db, sender_name, receiver_name)
            if ai_content:
                subject = ai_content["subject"]
                body_html = ai_content["body_html"]
                body_text = ai_content["body_text"]
                ai_generated = True
                ai_provider = ai_content.get("ai_provider", "")
            else:
                subject = generate_warmup_subject()
                body_text = generate_warmup_body(sender_name, receiver_name)
                body_html = "<p>" + body_text.replace(chr(10)+chr(10), "</p><p>").replace(chr(10), "<br>") + "</p>"
                ai_generated = False
                ai_provider = None

            tracking_id = str(uuid.uuid4())
            # Inject tracking pixel into HTML body for open tracking
            body_html = inject_tracking(body_html, tracking_id, db)

            result = send_warmup_email(mb, peer.email, subject, body_html, body_text)
            results["total"] += 1
            email_record = WarmupEmail(
                sender_mailbox_id=mb.mailbox_id,
                receiver_mailbox_id=peer.mailbox_id,
                subject=subject,
                body_html=body_html,
                body_text=body_text,
                message_id=result.get("message_id", ""),
                status=WarmupEmailStatus.SENT if result["success"] else WarmupEmailStatus.FAILED,
                tracking_id=tracking_id,
                ai_generated=ai_generated,
                ai_provider=ai_provider,
            )
            db.add(email_record)

            if result["success"]:
                results["sent"] += 1
                mb.emails_sent_today += 1
                mb.total_emails_sent += 1
                mb.warmup_emails_sent = (mb.warmup_emails_sent or 0) + 1
                peer.warmup_emails_received = (peer.warmup_emails_received or 0) + 1
            else:
                results["failed"] += 1

            results["details"].append({
                "sender": mb.email,
                "receiver": peer.email,
                "success": result["success"],
                "error": result.get("error"),
            })

    db.commit()
    return results


def run_auto_reply_cycle(db: Session) -> Dict[str, Any]:
    """Auto-reply to received warmup emails to boost reply rates and ISP reputation.

    Logic:
    - Find warmup emails that were SENT successfully but never replied to
    - Only reply to emails older than a random 15-90 min delay (looks natural)
    - The RECEIVER mailbox sends a reply back to the SENDER
    - Only reply to ~40-60% of emails (realistic reply rate)
    - Update replied_at, reply_count, warmup_replies counters
    """
    from app.services.warmup.content_generator import generate_warmup_reply
    from app.services.warmup.smart_scheduler import should_skip_weekend

    if should_skip_weekend(db):
        return {"skipped": True, "reason": "Weekend - skipping auto-replies"}

    enabled = _get_setting(db, "warmup_auto_reply_enabled", True)
    if not enabled:
        return {"skipped": True, "reason": "Auto-reply disabled"}

    reply_rate_target = float(_get_setting(db, "warmup_auto_reply_rate", 0.5))
    min_delay_minutes = int(_get_setting(db, "warmup_auto_reply_min_delay", 15))
    max_delay_minutes = int(_get_setting(db, "warmup_auto_reply_max_delay", 90))

    now = datetime.utcnow()
    delay_cutoff = now - timedelta(minutes=min_delay_minutes)

    # Find unreplied warmup emails that are old enough
    unreplied = db.query(WarmupEmail).filter(
        WarmupEmail.status == WarmupEmailStatus.SENT,
        WarmupEmail.replied_at.is_(None),
        WarmupEmail.receiver_mailbox_id.isnot(None),
        WarmupEmail.sent_at <= delay_cutoff,
        # Don't reply to emails older than 24h (already missed the window)
        WarmupEmail.sent_at >= now - timedelta(hours=24),
    ).all()

    results = {"total_candidates": len(unreplied), "replied": 0, "skipped": 0, "failed": 0, "details": []}

    for email_record in unreplied:
        # Randomly skip some emails to achieve a natural reply rate
        if random.random() > reply_rate_target:
            results["skipped"] += 1
            continue

        # Check if this email has been sitting long enough (random per-email delay)
        email_delay = random.randint(min_delay_minutes, max_delay_minutes)
        if email_record.sent_at and (now - email_record.sent_at).total_seconds() < email_delay * 60:
            results["skipped"] += 1
            continue

        # Get the receiver mailbox (the one who will send the reply)
        receiver_mb = db.query(SenderMailbox).filter(
            SenderMailbox.mailbox_id == email_record.receiver_mailbox_id,
            SenderMailbox.is_active == True,
            SenderMailbox.connection_status == "successful",
        ).first()
        if not receiver_mb:
            results["skipped"] += 1
            continue

        # Get the sender mailbox email (reply goes back to them)
        sender_mb = db.query(SenderMailbox).filter(
            SenderMailbox.mailbox_id == email_record.sender_mailbox_id,
        ).first()
        if not sender_mb:
            results["skipped"] += 1
            continue

        # Generate reply content
        replier_name = receiver_mb.display_name or receiver_mb.email.split("@")[0]
        reply_content = generate_warmup_reply(
            original_subject=email_record.subject or "",
            original_body=email_record.body_text or "",
            sender_name=replier_name,
            db=db,
        )

        # Send the reply
        send_result = send_warmup_email(
            receiver_mb, sender_mb.email,
            reply_content["subject"], reply_content["body_html"], reply_content["body_text"],
        )

        if send_result["success"]:
            # Update the original email record
            email_record.replied_at = now
            email_record.status = WarmupEmailStatus.REPLIED

            # Update sender mailbox counters (they received a reply)
            sender_mb.reply_count = (sender_mb.reply_count or 0) + 1
            sender_mb.warmup_replies = (sender_mb.warmup_replies or 0) + 1

            # Update receiver mailbox send counters
            receiver_mb.emails_sent_today = (receiver_mb.emails_sent_today or 0) + 1
            receiver_mb.total_emails_sent = (receiver_mb.total_emails_sent or 0) + 1
            receiver_mb.warmup_emails_sent = (receiver_mb.warmup_emails_sent or 0) + 1

            # Create a new email record for the reply itself
            reply_record = WarmupEmail(
                sender_mailbox_id=receiver_mb.mailbox_id,
                receiver_mailbox_id=sender_mb.mailbox_id,
                subject=reply_content["subject"],
                body_html=reply_content["body_html"],
                body_text=reply_content["body_text"],
                message_id=send_result.get("message_id", ""),
                status=WarmupEmailStatus.SENT,
                tracking_id=str(uuid.uuid4()),
                ai_generated=reply_content.get("ai_generated", False),
                ai_provider=reply_content.get("ai_provider") if reply_content.get("ai_generated") else None,
            )
            db.add(reply_record)

            results["replied"] += 1
            results["details"].append({
                "original_id": email_record.id,
                "replier": receiver_mb.email,
                "reply_to": sender_mb.email,
                "success": True,
            })
        else:
            results["failed"] += 1
            results["details"].append({
                "original_id": email_record.id,
                "replier": receiver_mb.email,
                "reply_to": sender_mb.email,
                "success": False,
                "error": send_result.get("error"),
            })

    db.commit()
    return results
