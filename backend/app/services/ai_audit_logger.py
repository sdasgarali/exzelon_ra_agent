"""AI Decision Audit Logger — tracks every AI call, decision, and action.

Every AI-powered operation MUST log through this service so there is a
complete audit trail of: what was asked, what the model returned, what
decision was made, and what action was taken.
"""
import hashlib
import json
from datetime import datetime
from typing import Any, Dict, Optional

import structlog
from sqlalchemy.orm import Session

logger = structlog.get_logger()


def log_ai_decision(
    db: Session,
    *,
    tenant_id: int,
    decision_type: str,
    model_provider: str = "unknown",
    model_name: str = "unknown",
    prompt_hash: str = "",
    prompt_preview: str = "",
    raw_response: str = "",
    parsed_result: Optional[Dict[str, Any]] = None,
    confidence: Optional[int] = None,
    action_taken: str = "",
    action_gated: bool = False,
    gate_reason: str = "",
    input_tokens: int = 0,
    output_tokens: int = 0,
    latency_ms: int = 0,
    contact_id: Optional[int] = None,
    campaign_id: Optional[int] = None,
    thread_id: Optional[str] = None,
    error: Optional[str] = None,
) -> None:
    """Log an AI decision to the automation_events table.

    Uses the existing AutomationEvent model to avoid adding new tables,
    storing structured data in the details JSON column.
    """
    try:
        from app.services.automation_logger import log_automation_event

        details = {
            "model_provider": model_provider,
            "model_name": model_name,
            "prompt_hash": prompt_hash,
            "prompt_preview": prompt_preview[:200] if prompt_preview else "",
            "response_preview": raw_response[:300] if raw_response else "",
            "parsed_result": parsed_result,
            "confidence": confidence,
            "action_taken": action_taken,
            "action_gated": action_gated,
            "gate_reason": gate_reason,
            "tokens": {"input": input_tokens, "output": output_tokens},
            "latency_ms": latency_ms,
            "contact_id": contact_id,
            "campaign_id": campaign_id,
            "thread_id": thread_id,
            "error": error,
        }

        status = "error" if error else ("gated" if action_gated else "success")

        log_automation_event(
            db,
            event_type=f"ai_{decision_type}",
            description=(
                f"AI {decision_type}: {action_taken}"
                if action_taken
                else f"AI {decision_type}: confidence={confidence}"
            ),
            details=details,
            status=status,
            source="ai_engine",
        )

        logger.info(
            "ai_decision_logged",
            decision_type=decision_type,
            confidence=confidence,
            action_taken=action_taken,
            action_gated=action_gated,
            model=model_provider,
        )
    except Exception as e:
        # Never let audit logging failures break the main flow
        logger.error("ai_audit_log_failed", error=str(e), decision_type=decision_type)


def hash_prompt(prompt: str) -> str:
    """Create a short hash of a prompt for audit tracking."""
    return hashlib.sha256(prompt.encode()).hexdigest()[:16]


def should_gate_action(
    confidence: int,
    action_type: str,
    min_confidence: int = 70,
) -> tuple[bool, str]:
    """Determine if an AI action should be gated (blocked for human review).

    Returns (should_gate, reason).
    True means the action should NOT proceed automatically.
    """
    # Always gate these action types regardless of confidence
    ALWAYS_GATE = {"mark_do_not_contact", "mark_unsubscribed", "send_reply"}

    if action_type in ALWAYS_GATE and confidence < min_confidence:
        return True, f"Action '{action_type}' requires confidence >= {min_confidence} (got {confidence})"

    # Gate anything below 50% confidence
    if confidence < 50:
        return True, f"Confidence too low ({confidence}%) for automatic action"

    return False, ""
