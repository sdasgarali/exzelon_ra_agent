"""Reply Intelligence — LLM-powered intent detection + next-best-action.

Replaces the keyword-only detect_intent() in ai_reply_agent_service.py with
a 2-tier approach: LLM classification first, keyword fallback second.
Uses structured schemas for validated outputs.
"""
from typing import Any, Dict, Optional

import structlog
from sqlalchemy.orm import Session

from app.services.ai_schemas import (
    ReplyClassification,
    parse_ai_json_response,
)
from app.services.ai_safety import sanitize_email_for_ai

logger = structlog.get_logger()

_INTENT_KEYWORDS = {
    "interested": [
        "interested", "tell me more", "sounds good", "let's talk",
        "schedule", "calendar", "when can we", "love to learn",
        "send me", "happy to chat", "available",
    ],
    "objection": [
        "not interested", "too expensive", "no budget", "bad timing",
        "already have", "not looking", "no need", "pass on this",
        "not a good fit", "we're set",
    ],
    "question": [
        "how does", "what is", "can you", "do you",
        "tell me about", "explain", "more info", "pricing",
        "what kind", "how many",
    ],
    "ooo": [
        "out of office", "on vacation", "away from", "be back",
        "auto-reply", "returning", "maternity", "paternity",
    ],
    "unsubscribe": [
        "unsubscribe", "remove me", "stop emailing", "opt out",
        "take me off", "don't contact",
    ],
}


def classify_reply(
    db: Session,
    email_body: str,
    contact_ctx: Dict[str, Any],
    tenant_id: int,
) -> Dict[str, Any]:
    """Classify a reply using LLM with keyword fallback.

    Tier 1: LLM classification via structured schema
    Tier 2: Keyword-based classification (fallback)
    """
    try:
        result = _classify_reply_llm(db, email_body, contact_ctx, tenant_id)
        if result:
            return result
    except Exception as e:
        logger.warning("llm_classification_failed", error=str(e))

    return classify_reply_keyword(email_body)


def classify_reply_keyword(text: str) -> Dict[str, Any]:
    """Keyword-based intent classification (deterministic fallback)."""
    sanitized = sanitize_email_for_ai(text, max_length=2000)
    text_lower = sanitized.lower()

    scores = {}
    for intent, keywords in _INTENT_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text_lower)
        if score > 0:
            scores[intent] = score

    if not scores:
        return {
            "intent": "unknown",
            "confidence": 30,
            "sentiment": "neutral",
            "has_meeting_intent": False,
            "has_unsubscribe_intent": False,
            "key_phrases": [],
            "reasoning": "No keyword matches found",
            "recommended_action": "escalate_to_human",
        }

    best_intent = max(scores, key=scores.get)
    confidence = min(90, 40 + scores[best_intent] * 15)

    meeting_words = ["schedule", "calendar", "call", "meet", "chat", "zoom"]
    has_meeting = any(w in text_lower for w in meeting_words)

    unsub_words = ["unsubscribe", "remove", "stop", "opt out"]
    has_unsub = any(w in text_lower for w in unsub_words)

    return {
        "intent": best_intent,
        "confidence": confidence,
        "sentiment": _infer_sentiment(best_intent),
        "has_meeting_intent": has_meeting,
        "has_unsubscribe_intent": has_unsub,
        "key_phrases": list(scores.keys()),
        "reasoning": f"Keyword match: {best_intent} ({scores[best_intent]} hits)",
        "recommended_action": _intent_to_action(best_intent, confidence),
    }


def _classify_reply_llm(
    db: Session,
    email_body: str,
    contact_ctx: Dict[str, Any],
    tenant_id: int,
) -> Optional[Dict[str, Any]]:
    """LLM-powered classification using structured schema."""
    from app.services.ai_sales_agent.prompt_registry import get_prompt
    from app.services.ai_resilience import call_ai_with_fallback

    prompt_tmpl = get_prompt("reply_classification")
    if not prompt_tmpl:
        return None

    contact = contact_ctx.get("contact", {})
    history = contact_ctx.get("history", {})
    campaign = contact_ctx.get("campaign", {})

    sanitized = sanitize_email_for_ai(email_body, max_length=2000)

    user_prompt = prompt_tmpl.render(
        contact_name=contact.get("name", "Unknown"),
        contact_title=contact.get("title", "Unknown"),
        company_name=contact_ctx.get("company", {}).get("name", "Unknown"),
        campaign_name=campaign.get("name", "Outreach"),
        emails_sent=history.get("emails_sent", 0),
        emails_replied=history.get("emails_replied", 0),
        email_body=sanitized,
    )

    raw = call_ai_with_fallback(
        db, tenant_id, "_call_api",
        [{"role": "user", "content": user_prompt}],
        system=prompt_tmpl.system_prompt,
        temperature=prompt_tmpl.temperature,
        max_tokens=prompt_tmpl.max_tokens,
        fallback_result=None,
    )

    if not raw:
        return None

    parsed, error = parse_ai_json_response(raw, ReplyClassification)
    if parsed:
        result = parsed.model_dump()
        # Convert enum values to strings for downstream compatibility
        if hasattr(result.get("intent"), "value"):
            result["intent"] = result["intent"].value
        if hasattr(result.get("recommended_action"), "value"):
            result["recommended_action"] = result["recommended_action"].value
        return result

    logger.warning("reply_classification_parse_failed", error=error)
    return None


def determine_next_action_rule_based(
    intent: str,
    confidence: int,
) -> Dict[str, Any]:
    """Deterministic next-best-action based on intent + confidence."""
    if confidence < 40:
        return {
            "action": "escalate_to_human",
            "confidence": confidence,
            "delay_hours": 0,
            "reasoning": f"Low confidence ({confidence}%) — needs human review",
            "requires_human_approval": True,
        }

    action_map = {
        "interested": {
            "action": "send_reply",
            "delay_hours": 0,
            "reasoning": "Prospect expressed interest — reply promptly",
            "requires_human_approval": confidence < 70,
        },
        "objection": {
            "action": "send_reply",
            "delay_hours": 2,
            "reasoning": "Objection received — address with value prop after brief delay",
            "requires_human_approval": True,
        },
        "question": {
            "action": "send_reply",
            "delay_hours": 0,
            "reasoning": "Question asked — answer promptly",
            "requires_human_approval": confidence < 70,
        },
        "ooo": {
            "action": "schedule_followup",
            "delay_hours": 72,
            "reasoning": "Out of office — schedule follow-up after return",
            "requires_human_approval": False,
        },
        "unsubscribe": {
            "action": "mark_unsubscribed",
            "delay_hours": 0,
            "reasoning": "Unsubscribe request — must comply",
            "requires_human_approval": True,
        },
        "do_not_contact": {
            "action": "mark_do_not_contact",
            "delay_hours": 0,
            "reasoning": "Do-not-contact request — must comply",
            "requires_human_approval": True,
        },
        "referral": {
            "action": "escalate_to_human",
            "delay_hours": 0,
            "reasoning": "Referral — human should follow up on new contact",
            "requires_human_approval": True,
        },
        "not_relevant": {
            "action": "no_action",
            "delay_hours": 0,
            "reasoning": "Not relevant reply — no action needed",
            "requires_human_approval": False,
        },
    }

    result = action_map.get(intent, {
        "action": "escalate_to_human",
        "delay_hours": 0,
        "reasoning": f"Unknown intent '{intent}' — needs human review",
        "requires_human_approval": True,
    })

    return {**result, "confidence": confidence}


def _infer_sentiment(intent: str) -> str:
    positive = {"interested", "referral"}
    negative = {"objection", "unsubscribe", "do_not_contact", "not_relevant"}
    return "positive" if intent in positive else "negative" if intent in negative else "neutral"


def _intent_to_action(intent: str, confidence: int) -> str:
    if confidence < 40:
        return "escalate_to_human"
    mapping = {
        "interested": "send_reply",
        "objection": "send_reply",
        "question": "send_reply",
        "ooo": "schedule_followup",
        "unsubscribe": "mark_unsubscribed",
        "do_not_contact": "mark_do_not_contact",
    }
    return mapping.get(intent, "escalate_to_human")
