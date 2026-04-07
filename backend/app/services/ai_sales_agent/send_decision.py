"""Send Decision Engine — structured go/no-go with reason codes.

Combines policy checks, scoring, content analysis, and domain throttling
into a single structured decision. Logged for every email attempt.
"""
from typing import Any, Dict, Optional

import structlog

from app.services.ai_sales_agent.policy_engine import evaluate_send_policy, evaluate_content_policy
from app.services.ai_sales_agent.scoring_engine import calculate_composite_score

logger = structlog.get_logger()


def make_send_decision(
    ctx: Dict[str, Any],
    spam_score: int = 0,
    similarity_score: float = 0.0,
    word_count: int = 0,
    policies: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Make a structured send/no-send decision.

    Args:
        ctx: Contact context from build_contact_context()
        spam_score: Content spam score (0-100)
        similarity_score: Content similarity to recent sends (0.0-1.0)
        word_count: Email word count
        policies: Resolved policies (uses defaults if None)

    Returns:
        Dict with: should_send, reason_codes, confidence, composite_score,
        reasoning, lead_score, engagement_score, engagement_level
    """
    all_codes = []

    # 1. Policy check
    policy_result = evaluate_send_policy(ctx, policies)
    if not policy_result["allowed"]:
        all_codes.extend(policy_result["reason_codes"])

    # 2. Content policy check
    if spam_score > 0 or similarity_score > 0 or word_count > 0:
        content_result = evaluate_content_policy(spam_score, similarity_score, word_count, policies)
        if not content_result["allowed"]:
            all_codes.extend(content_result["reason_codes"])

    # 3. Scoring (informational)
    scores = calculate_composite_score(ctx)

    should_send = len(all_codes) == 0

    return {
        "should_send": should_send,
        "reason_codes": all_codes,
        "confidence": 90 if should_send else 10,
        "composite_score": scores["composite"],
        "lead_score": scores["lead_score"],
        "engagement_score": scores["engagement_score"],
        "engagement_level": scores["engagement_level"],
        "reasoning": "; ".join(all_codes) if all_codes else "All checks passed",
    }
