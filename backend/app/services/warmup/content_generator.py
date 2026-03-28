"""AI Warmup Content Generator - uses existing AI adapters for varied warmup email content."""
import random
import json
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from app.core.settings_resolver import get_tenant_setting


CONTENT_CATEGORIES = [
    "meeting_followup", "project_update", "question", "introduction",
    "thank_you", "scheduling", "feedback_request", "resource_sharing",
]

SUBJECT_TEMPLATES = {
    "meeting_followup": ["Following up on our chat", "Great meeting today", "Quick follow-up"],
    "project_update": ["Project status update", "Quick update on progress", "FYI - Project milestone"],
    "question": ["Quick question for you", "Need your input", "Thoughts on this?"],
    "introduction": ["Nice to connect", "Great to meet you", "Reaching out"],
    "thank_you": ["Thanks for your help", "Appreciated your time", "Thank you!"],
    "scheduling": ["Can we find time to chat?", "Scheduling a quick call", "When works for you?"],
    "feedback_request": ["Would love your feedback", "Your thoughts?", "Quick review needed"],
    "resource_sharing": ["Thought you might find this useful", "Sharing a resource", "Check this out"],
}

BODY_TEMPLATES = {
    "meeting_followup": ['Hi {receiver_name},\n\nIt was great chatting with you earlier. I wanted to follow up.\n\nBest regards,\n{sender_name}', 'Hey {receiver_name},\n\nThanks for taking the time to meet today.\n\nCheers,\n{sender_name}'],
    "project_update": ['Hi {receiver_name},\n\nJust a quick update - we are making good progress.\n\nBest,\n{sender_name}'],
    "question": ['Hi {receiver_name},\n\nHope you are having a good day. Quick question - would love your perspective.\n\nThanks,\n{sender_name}'],
    "introduction": ['Hi {receiver_name},\n\nGreat to connect! Would love to find time to chat.\n\nBest,\n{sender_name}'],
    "thank_you": ['Hi {receiver_name},\n\nJust wanted to say thanks for your help.\n\nBest regards,\n{sender_name}'],
    "scheduling": ['Hi {receiver_name},\n\nWould you have time this week for a quick call?\n\nThanks,\n{sender_name}'],
    "feedback_request": ['Hi {receiver_name},\n\nI have been working on a proposal and would value your feedback.\n\nAppreciate it,\n{sender_name}'],
    "resource_sharing": ['Hi {receiver_name},\n\nI came across something relevant to you. Let me know what you think!\n\nBest,\n{sender_name}'],
}


def get_ai_adapter(db: Session, tenant_id=None):
    """Load configured AI provider from settings."""
    provider = get_tenant_setting(db, "warmup_ai_provider", tenant_id=tenant_id, default="groq")
    api_key_map = {"groq": "groq_api_key", "openai": "openai_api_key", "anthropic": "anthropic_api_key", "gemini": "gemini_api_key"}
    api_key = get_tenant_setting(db, api_key_map.get(provider, "groq_api_key"), tenant_id=tenant_id, default="")
    if not api_key:
        return None
    try:
        if provider == "groq":
            from app.services.adapters.ai.groq import GroqAdapter
            return GroqAdapter(api_key=api_key)
        elif provider == "openai":
            from app.services.adapters.ai.openai_adapter import OpenAIAdapter
            return OpenAIAdapter(api_key=api_key)
        elif provider == "anthropic":
            from app.services.adapters.ai.anthropic_adapter import AnthropicAdapter
            return AnthropicAdapter(api_key=api_key)
        elif provider == "gemini":
            from app.services.adapters.ai.gemini import GeminiAdapter
            return GeminiAdapter(api_key=api_key)
    except Exception:
        pass
    return None


def generate_warmup_subject(category: str = None) -> str:
    """Generate a random conversational subject line."""
    cat = category or random.choice(CONTENT_CATEGORIES)
    return random.choice(SUBJECT_TEMPLATES.get(cat, SUBJECT_TEMPLATES["meeting_followup"]))


def generate_warmup_body(sender_name: str, receiver_name: str, category: str = None) -> str:
    """Generate natural conversation body using templates."""
    cat = category or random.choice(CONTENT_CATEGORIES)
    body = random.choice(BODY_TEMPLATES.get(cat, BODY_TEMPLATES["meeting_followup"]))
    return body.format(sender_name=sender_name, receiver_name=receiver_name)


def generate_ai_warmup_content(db: Session, sender_name: str, receiver_name: str, category: str = None, tenant_id=None) -> Optional[Dict[str, Any]]:
    """Generate AI-powered warmup email content."""
    adapter = get_ai_adapter(db, tenant_id=tenant_id)
    if not adapter:
        return None
    cat = category or random.choice(CONTENT_CATEGORIES)
    temperature = float(get_tenant_setting(db, "warmup_ai_temperature", tenant_id=tenant_id, default=0.8))
    max_length = int(get_tenant_setting(db, "warmup_content_max_length", tenant_id=tenant_id, default=200))
    try:
        messages = [
            {"role": "system", "content": f"You are writing a casual internal business email. Keep it under {max_length} words. Category: {cat}"},
            {"role": "user", "content": f"Write a casual email from {sender_name} to {receiver_name}. Return SUBJECT: on first line, then blank line, then body."}
        ]
        result = adapter._call_api(messages, temperature=temperature, max_tokens=max_length * 2)
        result_lines = result.strip().split(chr(10), 1)
        subject = result_lines[0].replace("SUBJECT:", "").replace("Subject:", "").strip()
        body = result_lines[1].strip() if len(result_lines) > 1 else ""
        return {"subject": subject, "body_text": body, "body_html": "<p>" + body.replace(chr(10)+chr(10), "</p><p>") + "</p>", "ai_provider": type(adapter).__name__}
    except Exception:
        return None


def generate_warmup_reply(original_subject: str, original_body: str, sender_name: str, db: Session = None, tenant_id=None) -> Dict[str, str]:
    """Generate a reply to a warmup email, using AI when available."""
    subject = "Re: " + original_subject if not original_subject.startswith("Re:") else original_subject

    # Try AI-generated reply first
    if db:
        adapter = get_ai_adapter(db, tenant_id=tenant_id)
        if adapter:
            try:
                temperature = float(get_tenant_setting(db, "warmup_ai_temperature", tenant_id=tenant_id, default=0.8))
                messages = [
                    {"role": "system", "content": "You are writing a brief, casual reply to an internal business email. Keep it under 60 words. Be natural and conversational."},
                    {"role": "user", "content": f"Write a short reply from {sender_name} to this email:\n\nSubject: {original_subject}\n{original_body[:300]}\n\nJust the reply body, no subject line."}
                ]
                body = adapter._call_api(messages, temperature=temperature, max_tokens=150).strip()
                return {"subject": subject, "body_text": body, "body_html": "<p>" + body.replace(chr(10)+chr(10), "</p><p>").replace(chr(10), "<br>") + "</p>", "ai_generated": True}
            except Exception:
                pass

    # Fallback to templates
    replies = [
        f"Thanks for reaching out! Let me get back to you soon." + chr(10) + "Best," + chr(10) + f"{sender_name}",
        f"Appreciate the update! I will review shortly." + chr(10) + "Cheers," + chr(10) + f"{sender_name}",
        f"Great to hear from you! Let us connect on this." + chr(10) + "Regards," + chr(10) + f"{sender_name}",
        f"Got it, thanks for the heads up!" + chr(10) + "Talk soon," + chr(10) + f"{sender_name}",
        f"Thanks {sender_name.split()[0] if ' ' in sender_name else sender_name}! Will take a look." + chr(10) + "Best," + chr(10) + f"{sender_name}",
    ]
    body = random.choice(replies)
    return {"subject": subject, "body_text": body, "body_html": "<p>" + body.replace(chr(10), "<br>") + "</p>", "ai_generated": False}
