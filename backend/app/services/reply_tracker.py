"""IMAP reply tracker service for detecting outreach replies and UNSUBSCRIBE requests."""
import email
import imaplib
import re
from datetime import datetime
from email.utils import parseaddr
from typing import Dict, Any, Optional

import structlog
from sqlalchemy.orm import Session

from app.db.models.outreach import OutreachEvent, OutreachStatus
from app.db.models.sender_mailbox import SenderMailbox, WarmupStatus
from app.db.models.suppression import SuppressionList
from app.db.models.contact import ContactDetails

logger = structlog.get_logger()

UNSUBSCRIBE_PATTERNS = [
    r'\bunsubscribe\b',
    r'\bremove\s+me\b',
    r'\bstop\s+emailing\b',
    r'\bopt\s*out\b',
    r'\bdo\s+not\s+contact\b',
]


def _extract_text_body(msg: email.message.Message) -> str:
    """Extract text body from email, preferring text/plain over text/html."""
    if msg.is_multipart():
        text_part = None
        html_part = None
        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type == 'text/plain' and not text_part:
                charset = part.get_content_charset() or 'utf-8'
                try:
                    text_part = part.get_payload(decode=True).decode(charset, errors='replace')
                except Exception:
                    text_part = str(part.get_payload(decode=True))
            elif content_type == 'text/html' and not html_part:
                charset = part.get_content_charset() or 'utf-8'
                try:
                    html_part = part.get_payload(decode=True).decode(charset, errors='replace')
                except Exception:
                    html_part = str(part.get_payload(decode=True))
        return text_part or html_part or ''
    else:
        charset = msg.get_content_charset() or 'utf-8'
        try:
            return msg.get_payload(decode=True).decode(charset, errors='replace')
        except Exception:
            return str(msg.get_payload(decode=True))


def _is_unsubscribe(subject: str, body: str) -> bool:
    """Check if the reply is an unsubscribe request."""
    text = f"{subject} {body}".lower()
    for pattern in UNSUBSCRIBE_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


def _clean_message_id(msg_id: str) -> str:
    """Normalize a Message-ID header value."""
    if not msg_id:
        return ''
    return msg_id.strip().strip('<>').strip()


def check_replies_for_mailbox(mailbox: SenderMailbox, db: Session) -> Dict[str, Any]:
    """Check a single mailbox for replies to outreach emails via IMAP.

    Returns dict with counts: {replies_found, unsubscribes, errors}.
    """
    result = {"replies_found": 0, "unsubscribes": 0, "errors": 0, "mailbox": mailbox.email}

    imap_host = mailbox.imap_host or "outlook.office365.com"
    imap_port = mailbox.imap_port or 993

    try:
        imap = imaplib.IMAP4_SSL(imap_host, imap_port)
        imap.login(mailbox.email, mailbox.password)
        imap.select("INBOX")
    except Exception as e:
        logger.error("IMAP connection failed", mailbox=mailbox.email, error=str(e))
        result["errors"] += 1
        return result

    try:
        # Search for unseen messages
        status, msg_ids = imap.search(None, "UNSEEN")
        if status != "OK" or not msg_ids[0]:
            logger.info("No unseen messages", mailbox=mailbox.email)
            imap.logout()
            return result

        msg_id_list = msg_ids[0].split()
        logger.info("Found unseen messages", mailbox=mailbox.email, count=len(msg_id_list))

        # Get all our sent message_ids for this mailbox for matching
        sent_message_ids = {
            _clean_message_id(e.message_id): e
            for e in db.query(OutreachEvent).filter(
                OutreachEvent.sender_mailbox_id == mailbox.mailbox_id,
                OutreachEvent.status == OutreachStatus.SENT,
                OutreachEvent.message_id.isnot(None)
            ).all()
        }

        # Also build subject map for fallback matching
        sent_subjects = {}
        for ev in db.query(OutreachEvent).filter(
            OutreachEvent.sender_mailbox_id == mailbox.mailbox_id,
            OutreachEvent.status == OutreachStatus.SENT,
            OutreachEvent.subject.isnot(None)
        ).all():
            clean_subj = ev.subject.strip().lower()
            sent_subjects[clean_subj] = ev

        for mid in msg_id_list:
            try:
                status, data = imap.fetch(mid, "(RFC822)")
                if status != "OK":
                    continue

                raw_email = data[0][1]
                msg = email.message_from_bytes(raw_email)

                # Extract headers
                in_reply_to = msg.get("In-Reply-To", "")
                references = msg.get("References", "")
                reply_subject = msg.get("Subject", "")
                from_addr = parseaddr(msg.get("From", ""))[1]

                reply_body = _extract_text_body(msg)

                # Try to match by In-Reply-To or References header
                matched_event: Optional[OutreachEvent] = None

                if in_reply_to:
                    clean_ref = _clean_message_id(in_reply_to)
                    if clean_ref in sent_message_ids:
                        matched_event = sent_message_ids[clean_ref]

                if not matched_event and references:
                    for ref in references.split():
                        clean_ref = _clean_message_id(ref)
                        if clean_ref in sent_message_ids:
                            matched_event = sent_message_ids[clean_ref]
                            break

                # Fallback: subject matching (Re: <our subject>)
                if not matched_event and reply_subject:
                    clean_reply_subj = re.sub(r'^(re|fw|fwd):\s*', '', reply_subject, flags=re.IGNORECASE).strip().lower()
                    if clean_reply_subj in sent_subjects:
                        matched_event = sent_subjects[clean_reply_subj]

                if not matched_event:
                    continue

                # Update the outreach event with reply data
                matched_event.reply_subject = reply_subject[:500] if reply_subject else None
                matched_event.reply_body = reply_body[:10000] if reply_body else None
                matched_event.reply_detected_at = datetime.utcnow()
                matched_event.status = OutreachStatus.REPLIED

                # Update mailbox reply count
                mailbox.reply_count = (mailbox.reply_count or 0) + 1

                result["replies_found"] += 1
                logger.info("Reply detected",
                    mailbox=mailbox.email,
                    event_id=matched_event.event_id,
                    from_addr=from_addr,
                    subject=reply_subject
                )

                # Check for UNSUBSCRIBE
                if _is_unsubscribe(reply_subject or '', reply_body or ''):
                    contact = db.query(ContactDetails).filter(
                        ContactDetails.contact_id == matched_event.contact_id
                    ).first()

                    if contact:
                        existing = db.query(SuppressionList).filter(
                            SuppressionList.email == contact.email.lower()
                        ).first()

                        if not existing:
                            suppression = SuppressionList(
                                email=contact.email.lower(),
                                reason="unsubscribe_reply"
                            )
                            db.add(suppression)
                            logger.info("Contact added to suppression list",
                                email=contact.email,
                                reason="unsubscribe_reply",
                                event_id=matched_event.event_id
                            )

                    result["unsubscribes"] += 1

            except Exception as e:
                logger.error("Error processing message", mailbox=mailbox.email, error=str(e))
                result["errors"] += 1

        db.commit()

    except Exception as e:
        logger.error("IMAP search/process failed", mailbox=mailbox.email, error=str(e))
        result["errors"] += 1
    finally:
        try:
            imap.logout()
        except Exception:
            pass

    return result


def check_all_mailbox_replies(db: Session) -> Dict[str, Any]:
    """Check all active mailboxes with IMAP configured for replies.

    Returns summary dict: {checked, replies_found, unsubscribes, errors, details}.
    """
    summary = {"checked": 0, "replies_found": 0, "unsubscribes": 0, "errors": 0, "details": []}

    mailboxes = db.query(SenderMailbox).filter(
        SenderMailbox.is_active == True,
        SenderMailbox.warmup_status.in_([
            WarmupStatus.COLD_READY, WarmupStatus.ACTIVE,
            WarmupStatus.WARMING_UP, WarmupStatus.RECOVERING
        ])
    ).all()

    if not mailboxes:
        logger.info("No active mailboxes found for reply checking")
        return summary

    for mb in mailboxes:
        try:
            result = check_replies_for_mailbox(mb, db)
            summary["checked"] += 1
            summary["replies_found"] += result["replies_found"]
            summary["unsubscribes"] += result["unsubscribes"]
            summary["errors"] += result["errors"]
            summary["details"].append(result)
        except Exception as e:
            logger.error("Reply check failed for mailbox", mailbox=mb.email, error=str(e))
            summary["errors"] += 1

    logger.info("Reply check complete",
        checked=summary["checked"],
        replies=summary["replies_found"],
        unsubscribes=summary["unsubscribes"]
    )
    return summary
