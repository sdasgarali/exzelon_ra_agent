"""Per-contact AI email personalization at send time."""
import json
import structlog
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.core.settings_resolver import get_tenant_setting
from app.services.adapters.ai_content import get_ai_adapter

logger = structlog.get_logger()

DEFAULT_PERSONALIZATION_PROMPT = """You are an expert cold email personalizer for a staffing/recruitment agency.

Rewrite the given email to be uniquely personalized for this specific contact.

RULES:
1. Use the contact's profile naturally (name, title, company, industry, location, job context)
2. Maintain the core message, value proposition, and CTA from the original
3. Keep under 120 words — shorter is more human
4. Write as a busy sales pro typing between meetings
5. Vary sentence length — mix short (3-5 words) with longer ones
6. Include one natural imperfection (dash, ellipsis, parenthetical)
7. NEVER use: "I hope this finds you well", "reaching out", "cutting-edge", "synergy"
8. Use first-person observations: "I noticed", "I saw that"
9. Reference something specific about THEIR situation
10. Short paragraphs (1-2 sentences)

ANTI-AI-DETECTION:
- Write like a slightly rushed but professional human
- Mix contractions inconsistently
- Avoid uniform sentence length
- One imperfection makes it authentic

OUTPUT FORMAT (strict):
SUBJECT: [rewritten subject, under 50 chars]
---
[email body as HTML with <p> tags only]
---
[email body as plain text]"""


def personalize_email_for_contact(
    db: Session,
    tenant_id: Optional[int],
    subject: str,
    body_html: str,
    body_text: str,
    contact: Any,
    lead: Any,
) -> Dict[str, Any]:
    """Rewrite an email using AI, personalized for a specific contact.

    Returns a dict with keys: subject, body_html, body_text, ai_used, tokens_used.
    On any failure, returns the original content with ai_used=False (graceful fallback).
    """
    original = {
        "subject": subject,
        "body_html": body_html,
        "body_text": body_text,
        "ai_used": False,
        "tokens_used": 0,
    }

    # Check if AI personalization is enabled
    enabled = get_tenant_setting(
        db, "ai_personalize_emails", tenant_id=tenant_id, default="yes"
    )
    if str(enabled).lower() != "yes":
        return original

    # Get AI adapter — None means no API key configured
    adapter = get_ai_adapter(db, tenant_id)
    if adapter is None:
        return {**original, "ai_error": "no_ai_provider"}

    # Load custom or default personalization prompt
    system_prompt = get_tenant_setting(
        db,
        "ai_personalization_prompt",
        tenant_id=tenant_id,
        default=DEFAULT_PERSONALIZATION_PROMPT,
    )

    # Build contact profile for the AI
    profile = {
        "first_name": getattr(contact, "first_name", "") or "",
        "last_name": getattr(contact, "last_name", "") or "",
        "title": getattr(contact, "title", "") or "",
        "company": getattr(contact, "client_name", "") or "",
        "industry": "",
        "location": "",
        "job_title": "",
        "company_size": "",
    }
    if lead:
        profile["industry"] = getattr(lead, "industry", "") or ""
        profile["location"] = getattr(lead, "state", "") or ""
        profile["job_title"] = getattr(lead, "job_title", "") or ""
        profile["company_size"] = getattr(lead, "company_size", "") or ""
        if not profile["company"]:
            profile["company"] = getattr(lead, "client_name", "") or ""

    user_prompt = (
        f"ORIGINAL SUBJECT: {subject}\n\n"
        f"ORIGINAL BODY:\n{body_text}\n\n"
        f"CONTACT PROFILE:\n{json.dumps(profile, indent=2)}"
    )

    try:
        # Call adapter — handle Gemini's different signature
        from app.services.adapters.ai.gemini import GeminiAdapter

        if isinstance(adapter, GeminiAdapter):
            result = adapter._call_api(
                prompt=user_prompt,
                system_instruction=system_prompt,
                temperature=0.8,
                max_tokens=600,
            )
        else:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
            # Anthropic adapter accepts system kwarg
            from app.services.adapters.ai.anthropic_adapter import AnthropicAdapter

            if isinstance(adapter, AnthropicAdapter):
                result = adapter._call_api(
                    messages=[{"role": "user", "content": user_prompt}],
                    system=system_prompt,
                    temperature=0.8,
                    max_tokens=600,
                )
            else:
                result = adapter._call_api(
                    messages=messages,
                    temperature=0.8,
                    max_tokens=600,
                )

        tokens_used = 0
        if hasattr(adapter, "_last_usage") and adapter._last_usage:
            tokens_used = (
                adapter._last_usage.get("input_tokens", 0)
                + adapter._last_usage.get("output_tokens", 0)
            )

        # Parse the SUBJECT/---/body_html/---/body_text format
        parsed = _parse_personalized_response(result)
        if parsed:
            logger.info(
                "ai_personalization_applied",
                tenant_id=tenant_id,
                contact_id=getattr(contact, "contact_id", None),
                tokens_used=tokens_used,
            )
            return {
                "subject": parsed["subject"],
                "body_html": parsed["body_html"],
                "body_text": parsed["body_text"],
                "ai_used": True,
                "tokens_used": tokens_used,
            }

        # Parsing failed — fall back to original
        logger.warning(
            "ai_personalization_parse_failed",
            tenant_id=tenant_id,
            contact_id=getattr(contact, "contact_id", None),
        )
        return {**original, "ai_error": "parse_failed"}

    except Exception as e:
        logger.warning(
            "ai_personalization_failed",
            tenant_id=tenant_id,
            contact_id=getattr(contact, "contact_id", None),
            error=str(e),
        )
        return {**original, "ai_error": str(e)}


def _parse_personalized_response(text: str) -> Optional[Dict[str, str]]:
    """Parse SUBJECT: .../---/body_html/---/body_text from AI response."""
    try:
        parts = text.split("---")
        if len(parts) < 2:
            return None

        subject_line = parts[0].strip()
        if subject_line.upper().startswith("SUBJECT:"):
            subject_line = subject_line[len("SUBJECT:"):].strip()

        body_html = parts[1].strip()
        body_text = parts[2].strip() if len(parts) > 2 else ""

        if not subject_line or not body_html:
            return None

        # Generate plain text from HTML if not provided
        if not body_text:
            body_text = (
                body_html.replace("<p>", "")
                .replace("</p>", "\n")
                .replace("<br>", "\n")
                .replace("<br/>", "\n")
                .replace("<br />", "\n")
                .strip()
            )

        return {
            "subject": subject_line,
            "body_html": body_html,
            "body_text": body_text,
        }
    except Exception:
        return None
