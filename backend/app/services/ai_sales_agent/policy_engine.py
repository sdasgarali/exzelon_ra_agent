"""Deterministic Policy Engine — gates all AI actions with configurable rules.

Every AI action (send email, auto-reply, classify intent, etc.) passes through
this engine before execution. Rules are deterministic (no AI involved) and
configurable per tenant via settings_resolver.

Safety philosophy: deny by default, allow explicitly.
"""
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger()

DEFAULT_POLICIES: Dict[str, Any] = {
    # Send controls
    "max_emails_per_contact_per_day": 1,
    "max_contacts_per_company": 5,
    "cooldown_days": 10,
    "block_weekends": True,
    "require_valid_email": True,
    # Reply controls
    "min_confidence_auto_reply": 70,
    "min_confidence_auto_send": 80,
    "max_auto_replies_per_thread": 3,
    # Content controls
    "max_spam_score_to_send": 40,
    "min_content_uniqueness": 0.85,
    "max_email_words": 200,
    # AI controls
    "ai_autonomy_mode": "supervised",  # supervised | semi_auto | full_auto
    "always_gate_actions": ["mark_unsubscribed", "mark_do_not_contact"],
}

_DESTRUCTIVE_INTENTS = {"unsubscribe", "do_not_contact"}


def get_policies(
    db=None, tenant_id: Optional[int] = None, campaign=None,
) -> Dict[str, Any]:
    """Resolve policies from defaults + tenant overrides + campaign overrides."""
    policies = dict(DEFAULT_POLICIES)

    if db and tenant_id:
        try:
            from app.core.settings_resolver import get_tenant_setting
            for key in DEFAULT_POLICIES:
                val = get_tenant_setting(db, f"ai_policy_{key}", tenant_id=tenant_id, default=None)
                if val is not None:
                    default_type = type(DEFAULT_POLICIES[key])
                    if default_type == bool:
                        policies[key] = str(val).lower() in ("true", "1", "yes")
                    elif default_type == int:
                        try:
                            policies[key] = int(val)
                        except (ValueError, TypeError):
                            pass
                    else:
                        policies[key] = val
        except Exception as e:
            logger.warning("policy_tenant_resolution_failed", error=str(e))

    if campaign:
        if hasattr(campaign, "max_auto_replies_per_thread") and campaign.max_auto_replies_per_thread:
            policies["max_auto_replies_per_thread"] = campaign.max_auto_replies_per_thread

    return policies


def evaluate_send_policy(
    ctx: Dict[str, Any],
    policies: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Evaluate whether an email send is allowed.

    Returns: {allowed, reason_codes, reasoning}
    """
    p = {**DEFAULT_POLICIES, **(policies or {})}
    codes: List[str] = []

    contact = ctx.get("contact", {})
    history = ctx.get("history", {})

    # Rule 1: email must be valid
    if p["require_valid_email"] and contact.get("validation_status") not in ("Valid", "Catch-all"):
        codes.append("INVALID_EMAIL")

    # Rule 2: contact must not be unsubscribed
    if contact.get("outreach_status") == "UNSUBSCRIBED":
        codes.append("UNSUBSCRIBED")

    # Rule 3: contact must be active
    if contact.get("outreach_status") == "INACTIVE":
        codes.append("INACTIVE_CONTACT")

    # Rule 4: check negative reply history
    if history.get("emails_replied", 0) > 0 and history.get("last_reply_intent") not in (None, "ooo"):
        last_intent = history.get("last_reply_intent", "")
        if last_intent in ("not_interested", "do_not_contact"):
            codes.append("NEGATIVE_REPLY")

    return {
        "allowed": len(codes) == 0,
        "reason_codes": codes,
        "reasoning": "; ".join(codes) if codes else "All policy checks passed",
    }


def evaluate_reply_policy(
    intent: str,
    confidence: int,
    policies: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Evaluate whether an auto-reply should be sent or gated for review.

    Returns: {auto_send_allowed, reason_codes, suggested_delay_minutes}
    """
    p = {**DEFAULT_POLICIES, **(policies or {})}
    codes: List[str] = []
    min_conf = p.get("min_confidence_auto_reply", 70)

    # Rule 1: destructive intents always require human review
    if intent in _DESTRUCTIVE_INTENTS:
        codes.append("DESTRUCTIVE_ACTION")

    # Rule 2: confidence must exceed threshold
    if confidence < min_conf:
        codes.append("LOW_CONFIDENCE")

    auto_allowed = len(codes) == 0
    delay = 5 if auto_allowed else 0

    return {
        "auto_send_allowed": auto_allowed,
        "reason_codes": codes,
        "suggested_delay_minutes": delay,
        "reasoning": "; ".join(codes) if codes else "Auto-send approved",
    }


def evaluate_content_policy(
    spam_score: int = 0,
    similarity_score: float = 0.0,
    word_count: int = 0,
    policies: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Evaluate content quality policy before sending.

    Returns: {allowed, reason_codes, warnings}
    """
    p = {**DEFAULT_POLICIES, **(policies or {})}
    codes: List[str] = []
    warnings: List[str] = []

    if spam_score > p.get("max_spam_score_to_send", 40):
        codes.append("HIGH_SPAM_SCORE")

    if similarity_score > p.get("min_content_uniqueness", 0.85):
        codes.append("CONTENT_TOO_SIMILAR")

    if word_count > p.get("max_email_words", 200):
        warnings.append("EMAIL_TOO_LONG")

    return {
        "allowed": len(codes) == 0,
        "reason_codes": codes,
        "warnings": warnings,
    }
