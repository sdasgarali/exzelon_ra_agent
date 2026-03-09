"""Inbox message syncer — populates unified inbox from outreach events and replies."""
import hashlib
from datetime import datetime
from typing import Dict, Any
import structlog
from sqlalchemy.orm import Session

from app.db.models.inbox_message import InboxMessage, MessageDirection
from app.db.models.outreach import OutreachEvent, OutreachStatus
from app.db.models.contact import ContactDetails
from app.db.models.sender_mailbox import SenderMailbox

logger = structlog.get_logger()


def compute_thread_id(message_id: str = None, in_reply_to: str = None, contact_email: str = None, subject: str = None) -> str:
    """Compute a thread ID for grouping messages into conversations.

    Uses in_reply_to chain when available, falls back to email+subject hash.
    """
    if in_reply_to:
        return hashlib.md5(in_reply_to.encode()).hexdigest()[:20]
    if message_id:
        return hashlib.md5(message_id.encode()).hexdigest()[:20]
    # Fallback: hash of contact email + normalized subject
    key = f"{contact_email or ''}:{(subject or '').lower().replace('re:', '').strip()}"
    return hashlib.md5(key.encode()).hexdigest()[:20]


def sync_inbox(db: Session) -> Dict[str, Any]:
    """Sync outreach events into inbox_messages table.

    Creates InboxMessage(direction=SENT) for OutreachEvents missing inbox records.
    Creates InboxMessage(direction=RECEIVED) from detected replies.
    """
    results = {"sent_synced": 0, "replies_synced": 0, "errors": 0}

    # 1. Sync sent outreach events that don't have inbox records yet
    sent_events = db.query(OutreachEvent).filter(
        OutreachEvent.status == OutreachStatus.SENT,
        ~OutreachEvent.event_id.in_(
            db.query(InboxMessage.outreach_event_id).filter(
                InboxMessage.outreach_event_id.isnot(None)
            )
        ),
    ).limit(200).all()

    for event in sent_events:
        try:
            contact = db.query(ContactDetails).filter(
                ContactDetails.contact_id == event.contact_id
            ).first()
            mailbox = db.query(SenderMailbox).filter(
                SenderMailbox.mailbox_id == event.sender_mailbox_id
            ).first() if event.sender_mailbox_id else None

            thread_id = compute_thread_id(
                message_id=event.message_id,
                contact_email=contact.email if contact else None,
                subject=event.subject,
            )

            msg = InboxMessage(
                thread_id=thread_id,
                contact_id=event.contact_id,
                mailbox_id=event.sender_mailbox_id,
                outreach_event_id=event.event_id,
                campaign_id=event.campaign_id,
                direction=MessageDirection.SENT,
                from_email=mailbox.email if mailbox else "unknown",
                to_email=contact.email if contact else "unknown",
                subject=event.subject,
                body_html=event.body_html,
                body_text=event.body_text,
                raw_message_id=event.message_id,
                received_at=event.sent_at,
                is_read=True,
            )
            db.add(msg)
            results["sent_synced"] += 1
        except Exception as e:
            logger.error("Failed to sync sent event", event_id=event.event_id, error=str(e))
            results["errors"] += 1

    # 2. Sync replies (events that have reply_detected_at but no received inbox message)
    replied_events = db.query(OutreachEvent).filter(
        OutreachEvent.reply_detected_at.isnot(None),
        OutreachEvent.reply_body.isnot(None),
    ).limit(200).all()

    for event in replied_events:
        try:
            # Check if reply already synced
            existing_reply = db.query(InboxMessage).filter(
                InboxMessage.outreach_event_id == event.event_id,
                InboxMessage.direction == MessageDirection.RECEIVED,
            ).first()
            if existing_reply:
                continue

            contact = db.query(ContactDetails).filter(
                ContactDetails.contact_id == event.contact_id
            ).first()
            mailbox = db.query(SenderMailbox).filter(
                SenderMailbox.mailbox_id == event.sender_mailbox_id
            ).first() if event.sender_mailbox_id else None

            # Find the sent message's thread
            sent_inbox = db.query(InboxMessage).filter(
                InboxMessage.outreach_event_id == event.event_id,
                InboxMessage.direction == MessageDirection.SENT,
            ).first()

            thread_id = sent_inbox.thread_id if sent_inbox else compute_thread_id(
                message_id=event.message_id,
                contact_email=contact.email if contact else None,
                subject=event.subject,
            )

            reply_msg = InboxMessage(
                thread_id=thread_id,
                contact_id=event.contact_id,
                mailbox_id=event.sender_mailbox_id,
                outreach_event_id=event.event_id,
                campaign_id=event.campaign_id,
                direction=MessageDirection.RECEIVED,
                from_email=contact.email if contact else "unknown",
                to_email=mailbox.email if mailbox else "unknown",
                subject=event.reply_subject or f"Re: {event.subject or ''}",
                body_html=None,
                body_text=event.reply_body,
                in_reply_to=event.message_id,
                received_at=event.reply_detected_at,
                is_read=False,
            )
            # Auto-classify received messages with sentiment analysis
            try:
                from app.services.ai_sentiment import analyze_reply_sentiment
                sentiment_result = analyze_reply_sentiment(
                    event.reply_body,
                    event.reply_subject or "",
                    db,
                )
                reply_msg.category = sentiment_result["category"]
                reply_msg.sentiment = sentiment_result["sentiment"]
                # Log AI classification event
                if sentiment_result.get("confidence", 0) > 0:
                    try:
                        from app.services.automation_logger import log_automation_event
                        log_automation_event(
                            db, "ai_classify",
                            f"Classified reply as {sentiment_result['category']} ({sentiment_result['sentiment']})",
                            details={"contact_email": contact.email if contact else "unknown", **sentiment_result},
                        )
                    except Exception:
                        pass
            except Exception as e:
                logger.warning("Sentiment analysis failed during sync", event_id=event.event_id, error=str(e))

            db.add(reply_msg)
            results["replies_synced"] += 1

            # Deal automation: auto-create deal on interested reply + log activity
            try:
                from app.services.deal_automation import (
                    auto_create_deal_from_interested_reply,
                    auto_log_email_activity,
                    auto_advance_stage,
                )
                # Log the received email as deal activity
                auto_log_email_activity(
                    contact_id=event.contact_id,
                    event_type="email_received",
                    db=db,
                    details={
                        "subject": event.reply_subject or f"Re: {event.subject or ''}",
                        "from": contact.email if contact else "unknown",
                    },
                )
                # If "interested", auto-create deal
                if reply_msg.category == "interested":
                    auto_create_deal_from_interested_reply(
                        contact_id=event.contact_id,
                        db=db,
                        campaign_id=event.campaign_id,
                    )
                # Auto-advance deals on reply received
                from app.db.models.deal import Deal
                contact_deals = db.query(Deal).filter(
                    Deal.contact_id == event.contact_id,
                    Deal.is_archived == False,
                ).all()
                for deal in contact_deals:
                    auto_advance_stage(deal.deal_id, "reply_received", db)
            except Exception as e:
                logger.warning("Deal automation failed during inbox sync",
                               contact_id=event.contact_id, error=str(e))
        except Exception as e:
            logger.error("Failed to sync reply", event_id=event.event_id, error=str(e))
            results["errors"] += 1

    db.commit()
    logger.info("Inbox sync completed", results=results)
    return results


def backfill_inbox(db: Session) -> Dict[str, Any]:
    """One-time migration: populate inbox from all existing outreach events."""
    return sync_inbox(db)
