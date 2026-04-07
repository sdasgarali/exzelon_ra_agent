"""AI Reply Agent -- HITL and Autopilot auto-reply system.

When inbox receives a reply:
1. AI analyzes intent (interested/objection/question/ooo)
2. AI generates contextual response
3. Response stored as AIReplyDraft with status='pending'
4. HITL: User sees draft in inbox, clicks Approve/Edit/Reject
5. Autopilot: If campaign.auto_reply_enabled, auto-send after delay
"""
import structlog
from datetime import datetime, timedelta
from typing import Optional, Dict
from sqlalchemy.orm import Session

from app.db.models.ai_reply_draft import AIReplyDraft
from app.db.models.inbox_message import InboxMessage, MessageDirection
from app.db.models.campaign import Campaign
from app.db.models.contact import ContactDetails
from app.services.ai_safety import sanitize_email_for_ai, build_safe_ai_prompt

logger = structlog.get_logger()

INTENT_CATEGORIES = {
    "interested": [
        "interested", "tell me more", "sounds good", "let's talk",
        "schedule", "calendar", "when can we", "love to learn",
    ],
    "objection": [
        "not interested", "too expensive", "no budget", "bad timing",
        "already have", "not looking", "no need", "unsubscribe",
    ],
    "question": [
        "how does", "what is", "can you", "do you",
        "tell me about", "explain", "more info", "pricing",
    ],
    "ooo": [
        "out of office", "on vacation", "away from", "be back",
        "auto-reply", "returning",
    ],
}


def detect_intent(text: str) -> tuple:
    """Detect intent from reply text. Returns (intent, confidence)."""
    # Sanitize to strip injection patterns / HTML before keyword matching
    sanitized = sanitize_email_for_ai(text, max_length=2000)
    text_lower = sanitized.lower()
    scores = {}
    for intent, keywords in INTENT_CATEGORIES.items():
        score = sum(1 for kw in keywords if kw in text_lower)
        if score > 0:
            scores[intent] = score

    if not scores:
        return "unknown", 30

    best_intent = max(scores, key=scores.get)
    confidence = min(90, 40 + scores[best_intent] * 15)
    return best_intent, confidence


def generate_ai_reply_draft(
    db: Session,
    thread_id: str,
    received_message: InboxMessage,
    contact: Optional[ContactDetails],
    campaign: Optional[Campaign],
    tenant_id: int,
) -> Optional[AIReplyDraft]:
    """Generate an AI reply draft for a received message."""
    # Detect intent (sanitization happens inside detect_intent)
    body_text = received_message.body_text or ""
    sanitized_body = sanitize_email_for_ai(body_text)
    intent, confidence = detect_intent(body_text)

    # Skip OOO -- no reply needed
    if intent == "ooo":
        logger.info("skip_ooo_reply", thread_id=thread_id)
        return None

    # Check max auto-replies per thread
    existing_drafts = db.query(AIReplyDraft).filter(
        AIReplyDraft.thread_id == thread_id,
        AIReplyDraft.tenant_id == tenant_id,
        AIReplyDraft.status.in_(["approved", "auto_sent"]),
    ).count()

    max_replies = 3
    if campaign and hasattr(campaign, "max_auto_replies_per_thread"):
        max_replies = campaign.max_auto_replies_per_thread or 3

    if existing_drafts >= max_replies:
        logger.info("max_auto_replies_reached", thread_id=thread_id, count=existing_drafts)
        return None

    # Generate reply using AI
    try:
        from app.services.adapters.ai_content import get_ai_adapter

        adapter = get_ai_adapter(db)
        if not adapter:
            return _generate_rule_based_reply(
                db, thread_id, intent, confidence,
                received_message, contact, campaign, tenant_id,
            )

        contact_name = (
            f"{contact.first_name} {contact.last_name}".strip()
            if contact else "there"
        )
        contact_context = f"Contact: {contact_name}"
        if contact:
            if contact.title:
                contact_context += f", {contact.title}"
            if contact.client_name:
                contact_context += f" at {contact.client_name}"

        campaign_context = f"Campaign: {campaign.name}" if campaign else ""

        user_content = (
            "You are replying to a cold email response. "
            "Generate a professional, concise reply.\n\n"
            f"Detected intent: {intent} (confidence: {confidence}%)\n"
            f"{contact_context}\n"
            f"{campaign_context}\n\n"
            "Their message:\n"
        )

        guidelines = (
            "\n\nGuidelines:\n"
            "- If interested: Acknowledge interest, suggest next steps "
            "(meeting/call), be enthusiastic but professional\n"
            "- If objection: Address the concern respectfully, provide "
            "value proposition, don't be pushy\n"
            "- If question: Answer clearly and helpfully, relate back to value\n"
            "- Keep it under 100 words\n"
            "- Use plain text, no markdown\n"
            "- Be warm and conversational\n"
            "- Sign off with just a first name"
        )

        messages = build_safe_ai_prompt(
            system_prompt=(
                "You write professional cold email replies. "
                "Be concise, warm, and action-oriented."
            ),
            user_content=user_content + guidelines,
            sanitized_email=sanitized_body,
        )

        reply_text = adapter._call_api(messages, max_tokens=300)

        # Check if calendar link should be included
        calendar_text = ""
        if intent == "interested" and campaign:
            from app.db.models.user import User

            if campaign.created_by:
                creator = db.query(User).filter(
                    User.user_id == campaign.created_by
                ).first()
                if creator and hasattr(creator, "calendar_link") and creator.calendar_link:
                    calendar_text = (
                        "\n\nHere's my calendar link to find a time that works: "
                        f"{creator.calendar_link}"
                    )

        if calendar_text:
            reply_text = reply_text + calendar_text

    except Exception as e:
        logger.error("ai_reply_generation_failed", error=str(e))
        return _generate_rule_based_reply(
            db, thread_id, intent, confidence,
            received_message, contact, campaign, tenant_id,
        )

    # Determine auto-send timing — gated by confidence threshold
    auto_send_at = None
    status = "pending"
    if campaign and hasattr(campaign, "auto_reply_enabled") and campaign.auto_reply_enabled:
        # Only auto-send if confidence is high enough (default: 70%)
        min_auto_confidence = 70
        try:
            from app.core.settings_resolver import get_tenant_setting
            min_auto_confidence = int(get_tenant_setting(
                db, "ai_auto_reply_min_confidence",
                tenant_id=tenant_id, default=70,
            ))
        except Exception:
            pass

        if confidence >= min_auto_confidence:
            delay = getattr(campaign, "auto_reply_delay_minutes", 5) or 5
            auto_send_at = datetime.utcnow() + timedelta(minutes=delay)
        else:
            logger.info(
                "auto_reply_gated_low_confidence",
                confidence=confidence,
                threshold=min_auto_confidence,
                thread_id=thread_id,
            )

    # Log AI decision for audit trail
    try:
        from app.services.ai_audit_logger import log_ai_decision
        log_ai_decision(
            db,
            tenant_id=tenant_id,
            decision_type="reply_classification",
            prompt_preview=body_text[:200],
            parsed_result={"intent": intent, "confidence": confidence},
            confidence=confidence,
            action_taken="auto_reply_queued" if auto_send_at else "draft_pending_review",
            action_gated=auto_send_at is None and bool(
                campaign and hasattr(campaign, "auto_reply_enabled") and campaign.auto_reply_enabled
            ),
            gate_reason=f"confidence {confidence}% < {min_auto_confidence}%" if auto_send_at is None else "",
            contact_id=contact.contact_id if contact else None,
            campaign_id=campaign.campaign_id if campaign else None,
            thread_id=thread_id,
        )
    except Exception as e_audit:
        logger.warning("AI audit logging failed", error=str(e_audit))

    # Build subject
    subject = received_message.subject or ""
    if subject and not subject.lower().startswith("re:"):
        subject = f"Re: {subject}"

    # Create draft
    draft = AIReplyDraft(
        tenant_id=tenant_id,
        thread_id=thread_id,
        campaign_id=campaign.campaign_id if campaign else None,
        contact_id=contact.contact_id if contact else None,
        mailbox_id=received_message.mailbox_id,
        subject=subject,
        body_html=f"<p>{reply_text.replace(chr(10), '<br>')}</p>",
        body_text=reply_text,
        intent_detected=intent,
        confidence_score=confidence,
        ai_model_used="ai_adapter",
        status=status,
        expires_at=datetime.utcnow() + timedelta(hours=24),
    )
    db.add(draft)
    db.commit()
    db.refresh(draft)

    logger.info(
        "ai_reply_draft_created",
        draft_id=draft.draft_id,
        intent=intent,
        confidence=confidence,
    )
    return draft


def _generate_rule_based_reply(
    db: Session,
    thread_id: str,
    intent: str,
    confidence: int,
    msg: InboxMessage,
    contact: Optional[ContactDetails],
    campaign: Optional[Campaign],
    tenant_id: int,
) -> AIReplyDraft:
    """Fallback rule-based reply when AI is not available."""
    contact_name = contact.first_name if contact and contact.first_name else "there"

    templates = {
        "interested": (
            f"Hi {contact_name},\n\n"
            "Thanks for your interest! I'd love to schedule a quick call "
            "to discuss how we can help.\n\n"
            "Would any time this week work for a 15-minute chat?\n\n"
            "Best regards"
        ),
        "objection": (
            f"Hi {contact_name},\n\n"
            "I completely understand. Thanks for letting me know.\n\n"
            "If anything changes in the future, don't hesitate to reach out. "
            "I'm always happy to help.\n\n"
            "Best regards"
        ),
        "question": (
            f"Hi {contact_name},\n\n"
            "Great question! I'd be happy to provide more details.\n\n"
            "Would it be easier to jump on a quick call to discuss? "
            "I can walk you through everything.\n\n"
            "Best regards"
        ),
        "unknown": (
            f"Hi {contact_name},\n\n"
            "Thanks for getting back to me!\n\n"
            "I'd love to connect and discuss further. "
            "Would you be available for a brief call this week?\n\n"
            "Best regards"
        ),
    }

    reply_text = templates.get(intent, templates["unknown"])

    # Build subject
    subject = msg.subject or ""
    if subject and not subject.lower().startswith("re:"):
        subject = f"Re: {subject}"

    draft = AIReplyDraft(
        tenant_id=tenant_id,
        thread_id=thread_id,
        campaign_id=campaign.campaign_id if campaign else None,
        contact_id=contact.contact_id if contact else None,
        mailbox_id=msg.mailbox_id,
        subject=subject,
        body_html=f"<p>{reply_text.replace(chr(10), '<br>')}</p>",
        body_text=reply_text,
        intent_detected=intent,
        confidence_score=confidence,
        ai_model_used="rule_based",
        status="pending",
        expires_at=datetime.utcnow() + timedelta(hours=24),
    )
    db.add(draft)
    db.commit()
    db.refresh(draft)
    return draft


def process_auto_reply_queue(db: Session):
    """Scheduler job: send auto-approved drafts that have reached their delay.
    Called every minute.
    """
    now = datetime.utcnow()

    # Find pending drafts that haven't expired
    pending_drafts = db.query(AIReplyDraft).filter(
        AIReplyDraft.status == "pending",
        AIReplyDraft.expires_at > now,
    ).all()

    sent_count = 0
    for draft in pending_drafts:
        if not draft.campaign_id:
            continue

        campaign = db.query(Campaign).filter(
            Campaign.campaign_id == draft.campaign_id
        ).first()
        if not campaign or not getattr(campaign, "auto_reply_enabled", False):
            continue

        delay = getattr(campaign, "auto_reply_delay_minutes", 5) or 5
        send_after = draft.created_at + timedelta(minutes=delay)

        if now >= send_after:
            # Auto-send
            success = _send_draft(db, draft)
            if success:
                draft.status = "auto_sent"
                draft.sent_at = now
                sent_count += 1
                logger.info(
                    "auto_reply_sent",
                    draft_id=draft.draft_id,
                    thread_id=draft.thread_id,
                )

    db.commit()
    return {"processed": len(pending_drafts), "sent": sent_count}


def _send_draft(db: Session, draft: AIReplyDraft) -> bool:
    """Send a draft reply via SMTP."""
    try:
        from app.db.models.sender_mailbox import SenderMailbox

        mailbox = db.query(SenderMailbox).filter(
            SenderMailbox.mailbox_id == draft.mailbox_id
        ).first()
        if not mailbox:
            logger.warning("draft_send_no_mailbox", draft_id=draft.draft_id)
            return False

        # Determine recipient from last received message in thread
        last_received = db.query(InboxMessage).filter(
            InboxMessage.thread_id == draft.thread_id,
            InboxMessage.direction == MessageDirection.RECEIVED,
        ).order_by(InboxMessage.received_at.desc()).first()

        if not last_received:
            logger.warning("draft_send_no_received_message", draft_id=draft.draft_id)
            return False

        to_email = last_received.from_email

        from app.services.pipelines.outreach import send_outreach_email

        result = send_outreach_email(
            sender_mailbox=mailbox,
            to_email=to_email,
            subject=draft.subject,
            body_html=draft.body_html,
            body_text=draft.body_text,
            db=db,
        )

        if result.get("success"):
            # Record in inbox
            sent_msg = InboxMessage(
                thread_id=draft.thread_id,
                contact_id=draft.contact_id,
                mailbox_id=draft.mailbox_id,
                campaign_id=draft.campaign_id,
                direction=MessageDirection.SENT,
                from_email=mailbox.email,
                to_email=to_email,
                subject=draft.subject,
                body_html=draft.body_html,
                body_text=draft.body_text,
                raw_message_id=result.get("message_id"),
                received_at=datetime.utcnow(),
                is_read=True,
                tenant_id=draft.tenant_id,
            )
            db.add(sent_msg)
            return True
        return False
    except Exception as e:
        logger.error("draft_send_failed", draft_id=draft.draft_id, error=str(e))
        return False
