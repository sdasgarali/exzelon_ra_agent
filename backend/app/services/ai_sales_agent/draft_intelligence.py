"""Draft Intelligence — context-aware email generation with strategy planning.

Enhances the existing email generation by:
1. Building full context before drafting
2. Planning personalization strategy
3. Generating with structured output
4. Validating content quality
"""
from typing import Any, Dict, Optional

import structlog
from sqlalchemy.orm import Session

from app.services.ai_schemas import PersonalizationPlan, parse_ai_json_response

logger = structlog.get_logger()


def plan_personalization(
    ctx: Dict[str, Any],
    step_number: int = 1,
    db: Session = None,
    tenant_id: int = None,
) -> Dict[str, Any]:
    """Plan the personalization strategy for an email.

    Uses LLM if available, falls back to rule-based approach.
    """
    if db and tenant_id:
        try:
            result = _plan_with_llm(ctx, step_number, db, tenant_id)
            if result:
                return result
        except Exception as e:
            logger.warning("personalization_plan_llm_failed", error=str(e))

    return _plan_rule_based(ctx, step_number)


def _plan_rule_based(ctx: Dict[str, Any], step_number: int) -> Dict[str, Any]:
    """Rule-based personalization planning."""
    history = ctx.get("history", {})
    lead = ctx.get("lead", {})
    engagement = history.get("emails_replied", 0)

    if step_number == 1:
        angle = "hiring_need"
        max_words = 120
        cta_type = "soft"
    elif step_number == 2:
        angle = "value_add"
        max_words = 80
        cta_type = "soft"
    elif step_number == 3:
        angle = "social_proof"
        max_words = 60
        cta_type = "direct"
    else:
        angle = "break_up"
        max_words = 50
        cta_type = "none"

    hooks = []
    if lead.get("job_title"):
        hooks.append(f"Open role: {lead['job_title']}")
    if lead.get("city") and lead.get("state"):
        hooks.append(f"Location: {lead['city']}, {lead['state']}")
    if ctx.get("company", {}).get("industry"):
        hooks.append(f"Industry: {ctx['company']['industry']}")

    tone = "professional"
    if engagement > 0:
        tone = "consultative"
    if step_number >= 4:
        tone = "casual"

    return {
        "angle": angle,
        "tone": tone,
        "hooks": hooks[:3],
        "avoid": ["hype", "feature dumps", "exclamation marks"],
        "max_words": max_words,
        "include_cta": step_number < 4,
        "cta_type": cta_type,
    }


def _plan_with_llm(
    ctx: Dict[str, Any], step_number: int, db: Session, tenant_id: int,
) -> Optional[Dict[str, Any]]:
    """LLM-powered personalization planning."""
    from app.services.ai_sales_agent.prompt_registry import get_prompt
    from app.services.ai_resilience import call_ai_with_fallback

    prompt_tmpl = get_prompt("personalization_plan")
    if not prompt_tmpl:
        return None

    contact = ctx.get("contact", {})
    lead = ctx.get("lead", {})
    company = ctx.get("company", {})
    history = ctx.get("history", {})

    user_prompt = prompt_tmpl.render(
        contact_name=contact.get("name", "Unknown"),
        contact_title=contact.get("title", "Unknown"),
        company_name=company.get("name", "Unknown"),
        industry=company.get("industry", "Unknown"),
        job_title=lead.get("job_title", "Unknown"),
        location=f"{lead.get('city', '') or ''}, {lead.get('state', '') or ''}".strip(", "),
        company_size=company.get("size", "Unknown"),
        step_number=step_number,
        engagement_level=history.get("engagement_level", "cold"),
        objections=", ".join(history.get("objections", [])) or "None",
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

    parsed, error = parse_ai_json_response(raw, PersonalizationPlan)
    if parsed:
        return parsed.model_dump()

    logger.warning("personalization_plan_parse_failed", error=error)
    return None
