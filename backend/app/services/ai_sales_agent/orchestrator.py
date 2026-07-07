"""Agent Orchestrator — coordinates all AI sales-agent modules.

Two main entry points:
1. orchestrate_send() — called before sending an email
2. orchestrate_reply() — called when a reply is received
"""
from typing import Any, Dict

import structlog
from sqlalchemy.orm import Session

from app.services.ai_sales_agent.agent_context import (
    build_contact_context, build_interaction_history,
)
from app.services.ai_sales_agent.policy_engine import (
    get_policies, evaluate_reply_policy,
)
from app.services.ai_sales_agent.send_decision import make_send_decision
from app.services.ai_sales_agent.reply_intelligence import (
    classify_reply, determine_next_action_rule_based,
)
from app.services.ai_audit_logger import log_ai_decision

logger = structlog.get_logger()


def orchestrate_send(
    db: Session,
    contact,
    lead,
    campaign,
    tenant_id: int,
    step_number: int = 1,
    spam_score: int = 0,
    similarity_score: float = 0.0,
    word_count: int = 0,
) -> Dict[str, Any]:
    """Orchestrate the send decision for an outbound email.

    Steps:
    1. Build full context (contact + lead + company + history)
    2. Resolve tenant policies
    3. Make structured send decision (policy + scoring + content)
    4. Plan personalization if approved
    5. Log the decision for audit
    """
    # 1. Build context
    history = build_interaction_history(db, contact.contact_id, tenant_id)
    ctx = build_contact_context(
        contact=contact, lead=lead, history=history, campaign=campaign,
    )

    # 2. Resolve policies
    policies = get_policies(db, tenant_id, campaign)

    # 3. Make decision
    decision = make_send_decision(
        ctx, spam_score=spam_score, similarity_score=similarity_score,
        word_count=word_count, policies=policies,
    )

    # 4. Plan personalization if sending
    personalization = None
    if decision["should_send"]:
        try:
            from app.services.ai_sales_agent.draft_intelligence import plan_personalization
            personalization = plan_personalization(ctx, step_number, db, tenant_id)
        except Exception as e:
            logger.warning("personalization_planning_failed", error=str(e))

    # 5. Audit log
    try:
        log_ai_decision(
            db,
            tenant_id=tenant_id,
            decision_type="send_decision",
            parsed_result={
                "should_send": decision["should_send"],
                "reason_codes": decision["reason_codes"],
                "composite_score": decision.get("composite_score"),
            },
            confidence=decision["confidence"],
            action_taken="send_approved" if decision["should_send"] else "send_blocked",
            action_gated=not decision["should_send"],
            gate_reason=decision.get("reasoning", ""),
            contact_id=contact.contact_id,
            campaign_id=campaign.campaign_id if campaign else None,
        )
    except Exception:
        pass

    result = {**decision}
    if personalization:
        result["personalization_plan"] = personalization
    return result


def orchestrate_reply(
    db: Session,
    email_body: str,
    contact,
    campaign,
    tenant_id: int,
) -> Dict[str, Any]:
    """Orchestrate the reply handling workflow.

    Steps:
    1. Build full context
    2. Classify reply intent (LLM with keyword fallback)
    3. Determine next-best-action (rule-based)
    4. Evaluate reply policy (gate auto-actions)
    5. Log the decision
    """
    # 1. Build context
    history = {}
    if contact and hasattr(contact, "contact_id"):
        history = build_interaction_history(db, contact.contact_id, tenant_id)
    ctx = build_contact_context(
        contact=contact, lead=None, history=history, campaign=campaign,
    )

    # 2. Classify intent
    classification = classify_reply(db, email_body, ctx, tenant_id)
    intent = classification.get("intent", "unknown")
    confidence = classification.get("confidence", 30)

    # 3. Next-best-action
    nba = determine_next_action_rule_based(intent, confidence)

    # 4. Policy gate
    policies = get_policies(db, tenant_id, campaign)
    policy_result = evaluate_reply_policy(intent, confidence, policies)

    # 5. Audit log
    try:
        log_ai_decision(
            db,
            tenant_id=tenant_id,
            decision_type="reply_classification",
            parsed_result={
                "intent": intent,
                "confidence": confidence,
                "next_action": nba["action"],
            },
            confidence=confidence,
            action_taken=nba["action"],
            action_gated=not policy_result["auto_send_allowed"],
            gate_reason="; ".join(policy_result.get("reason_codes", [])),
            contact_id=contact.contact_id if contact and hasattr(contact, "contact_id") else None,
            campaign_id=campaign.campaign_id if campaign and hasattr(campaign, "campaign_id") else None,
        )
    except Exception:
        pass

    return {
        "intent": intent,
        "confidence": confidence,
        "sentiment": classification.get("sentiment", "neutral"),
        "classification": classification,
        "next_action": nba,
        "policy_result": policy_result,
    }
