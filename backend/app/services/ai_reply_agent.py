"""AI reply agent — generates suggested replies for inbox conversations."""
import structlog
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from app.db.models.inbox_message import InboxMessage
from app.db.models.contact import ContactDetails
from app.db.models.campaign import Campaign

logger = structlog.get_logger()


def generate_reply_suggestion(
    thread_messages: List[InboxMessage],
    contact: Optional[ContactDetails],
    campaign: Optional[Campaign],
    db: Session,
) -> Dict[str, Any]:
    """Generate an AI-suggested reply for an inbox thread.

    Returns {subject, body_html, body_text, confidence}.
    """
    # Build conversation context
    conversation = []
    for msg in thread_messages[-5:]:  # last 5 messages
        direction = "We sent" if msg.direction.value == "sent" else "They replied"
        conversation.append(f"{direction}: {msg.body_text or msg.subject or ''}")

    contact_context = ""
    if contact:
        contact_context = (
            f"Contact: {contact.first_name} {contact.last_name}, "
            f"Title: {contact.title or 'Unknown'}, "
            f"Company: {contact.client_name or 'Unknown'}"
        )

    campaign_context = ""
    if campaign:
        campaign_context = f"Campaign: {campaign.name}"

    prompt = (
        "You are writing a professional follow-up reply for a B2B cold email conversation. "
        "Be concise, friendly, and action-oriented.\n\n"
        f"{contact_context}\n"
        f"{campaign_context}\n\n"
        "Conversation so far:\n"
        + "\n".join(conversation)
        + "\n\nWrite a brief, professional reply. Include a clear call-to-action. "
        "Do NOT include subject line, greeting, or signature — just the body text."
    )

    try:
        from app.services.adapters.ai_content import get_ai_adapter
        adapter = get_ai_adapter(db)

        if not adapter:
            return _fallback_reply(contact)

        response = adapter._call_api(
            [{"role": "user", "content": prompt}],
            max_tokens=300,
        )
        if not response:
            return _fallback_reply(contact)

        body_text = response.strip()
        body_html = f"<p>{body_text.replace(chr(10), '</p><p>')}</p>"

        # Determine subject
        last_subject = ""
        for msg in reversed(thread_messages):
            if msg.subject:
                last_subject = msg.subject
                break
        subject = last_subject if last_subject.lower().startswith("re:") else f"Re: {last_subject}"

        # Log AI suggestion event
        try:
            from app.services.automation_logger import log_automation_event
            contact_name = f"{contact.first_name} {contact.last_name}" if contact else "unknown"
            log_automation_event(
                db, "ai_suggest",
                f"AI reply suggestion generated for {contact_name}",
                details={"contact": contact_name, "confidence": 0.8},
                source="user",
            )
        except Exception:
            pass

        return {
            "subject": subject,
            "body_html": body_html,
            "body_text": body_text,
            "confidence": 0.8,
        }

    except Exception as e:
        logger.error("AI reply generation failed", error=str(e))
        return _fallback_reply(contact)


def _fallback_reply(contact: Optional[ContactDetails]) -> Dict[str, Any]:
    """Fallback reply when AI is unavailable."""
    name = contact.first_name if contact else "there"
    body = f"Hi {name},\n\nThank you for your reply. I'd love to discuss this further. Would you be available for a quick call this week?\n\nBest regards"
    return {
        "subject": "",
        "body_html": f"<p>{body.replace(chr(10), '</p><p>')}</p>",
        "body_text": body,
        "confidence": 0.3,
    }
