"""AI Sequence Generator — creates multi-step email campaign sequences."""
import json
import re
import structlog
from typing import Dict, Any, List, Optional

from sqlalchemy.orm import Session

logger = structlog.get_logger()


def generate_sequence(
    goal: str,
    product: str,
    tone: str = "professional",
    num_steps: int = 4,
    db: Optional[Session] = None,
    tenant_id: Optional[int] = None,
    lob_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Generate an email sequence using AI.

    Falls back to template-based generation if AI is unavailable.

    Args:
        goal: Campaign goal (e.g., "book meetings", "generate leads")
        product: Product/service being promoted
        tone: Email tone (professional, casual, urgent, friendly)
        num_steps: Number of email steps (2-6)
        db: Database session (required for AI path)
        tenant_id: Tenant context for AI adapter lookup
        lob_id: Line of Business ID for LOB-specific prompt context

    Returns:
        List of step dicts: [{step_order, step_type, subject, body_html, delay_days, delay_hours}]
    """
    num_steps = max(2, min(6, num_steps))

    if db is not None:
        try:
            return _generate_with_ai(goal, product, tone, num_steps, db, tenant_id, lob_id)
        except Exception as e:
            logger.warning("AI sequence generation failed, using template fallback", error=str(e))

    return _generate_template_based(goal, product, tone, num_steps)


def _get_lob_context_for_sequence(db: Session, lob_id: Optional[int]) -> tuple:
    """Retrieve LOB type and description for sequence generation.

    Returns:
        (company_description, value_proposition, lob_type)
    """
    if lob_id is None:
        return "a staffing/recruitment agency", "", "staffing"

    from app.db.models.line_of_business import LineOfBusiness
    from app.services.ai_sales_agent.prompt_registry import LOB_DEFAULT_PROFILES

    lob = db.query(LineOfBusiness).filter(LineOfBusiness.lob_id == lob_id).first()
    if not lob:
        return "a staffing/recruitment agency", "", "staffing"

    lob_type = lob.lob_type.value if hasattr(lob.lob_type, 'value') else str(lob.lob_type)
    defaults = LOB_DEFAULT_PROFILES.get(lob_type, LOB_DEFAULT_PROFILES.get("staffing", {}))

    # Overlay custom prompt_profile if present
    import json as _json
    profile = {**defaults}
    if lob.prompt_profile:
        try:
            custom = _json.loads(lob.prompt_profile)
            if isinstance(custom, dict):
                profile.update({k: v for k, v in custom.items() if v})
        except (ValueError, TypeError):
            pass

    return (
        profile.get("company_description", "a B2B services company"),
        profile.get("value_proposition", ""),
        lob_type,
    )


def _generate_with_ai(
    goal: str,
    product: str,
    tone: str,
    num_steps: int,
    db: Session,
    tenant_id: Optional[int] = None,
    lob_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Use AI adapter to generate email sequence."""
    from app.services.adapters.ai_content import get_ai_adapter
    from app.services.adapters.ai.prompts import OUTREACH_SYSTEM_PROMPT

    adapter = get_ai_adapter(db, tenant_id=tenant_id)
    if adapter is None:
        raise RuntimeError("No AI adapter configured")

    company_desc, value_prop, lob_type = _get_lob_context_for_sequence(db, lob_id)
    value_prop_line = f"\n**Value Proposition:** {value_prop}" if value_prop else ""

    prompt = f"""Create a {num_steps}-step cold email sequence for {company_desc}.

**Campaign Goal:** {goal}
**Product/Service:** {product}
**Tone:** {tone}
**Steps:** {num_steps}{value_prop_line}

For each step, return a JSON array of objects with:
- "step_order": 1-based integer
- "step_type": "email" for email steps
- "subject": email subject line (use {{{{contact_first_name}}}} and {{{{company_name}}}} placeholders)
- "body_html": HTML email body with <p> tags and placeholders ({{{{contact_first_name}}}}, {{{{company_name}}}}, {{{{contact_title}}}}, {{{{signature}}}})
- "delay_days": days to wait before this step (0 for first, 3 for second, 7 for third, 14 for break-up)
- "delay_hours": additional hours (0 for most)

Rules:
- First email: introduce the value proposition tied to the prospect's pain points
- Follow-ups: completely different angles, do NOT reference previous emails
- Last email: break-up style, gracious, leave the door open
- Keep each email under 120 words
- Short paragraphs (1-2 sentences each)
- No hype, no fluff, no exclamation marks
- Plain, direct, human-sounding
- CTA should be easy and low-pressure

Anti-AI-Detection (critical — emails WILL be flagged if you ignore these):
- Write as if a busy sales rep typed this on their phone between meetings
- Vary sentence length — mix very short (3-5 words) with longer sentences
- Include one natural imperfection per email (a dash, ellipsis, or parenthetical aside)
- NEVER start with "I hope this email finds you well" or "I wanted to reach out"
- Use first-person observations: "I noticed", "I saw that", "Something caught my eye"
- Contractions are fine but don't use them consistently — mix "I'm" and "I am" naturally
- Avoid uniform sentence length — humans write in bursts

Return ONLY a JSON array, no markdown or other text."""

    # Call the adapter using the appropriate method for each adapter type
    if hasattr(adapter, '_call_api'):
        # Groq, OpenAI, Anthropic use messages-based _call_api
        from app.services.adapters.ai.gemini import GeminiAdapter
        if isinstance(adapter, GeminiAdapter):
            text = adapter._call_api(
                prompt=prompt,
                system_instruction=OUTREACH_SYSTEM_PROMPT,
                max_tokens=1500,
            )
        else:
            # Check if it's Anthropic (uses system= kwarg)
            from app.services.adapters.ai.anthropic_adapter import AnthropicAdapter
            if isinstance(adapter, AnthropicAdapter):
                text = adapter._call_api(
                    messages=[{"role": "user", "content": prompt}],
                    system=OUTREACH_SYSTEM_PROMPT,
                    max_tokens=1500,
                )
            else:
                # Groq and OpenAI
                text = adapter._call_api(
                    messages=[
                        {"role": "system", "content": OUTREACH_SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    max_tokens=1500,
                )
    else:
        raise RuntimeError("Adapter does not support _call_api")

    # Extract JSON from response
    cleaned = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`")
    steps = json.loads(cleaned)

    # Validate and normalize
    for i, step in enumerate(steps):
        step["step_order"] = i + 1
        step.setdefault("step_type", "email")
        step.setdefault("subject", f"Follow-up #{i + 1}")
        step.setdefault("body_html", "")
        step.setdefault("delay_days", 0 if i == 0 else 3)
        step.setdefault("delay_hours", 0)

    return steps


def _generate_template_based(goal: str, product: str, tone: str, num_steps: int) -> List[Dict[str, Any]]:
    """Template-based fallback sequence generation."""
    templates = {
        2: [
            {
                "step_order": 1, "step_type": "email", "delay_days": 0, "delay_hours": 0,
                "subject": "Quick question about {{company_name}}",
                "body_html": (
                    "<p>Hi {{contact_first_name}},</p>"
                    f"<p>I came across {{{{company_name}}}} and wanted to reach out about {product}.</p>"
                    f"<p>{goal} — would you be open to a quick chat this week?</p>"
                    "<p>Best,</p>{{signature}}"
                ),
            },
            {
                "step_order": 2, "step_type": "email", "delay_days": 4, "delay_hours": 0,
                "subject": "Re: Quick question about {{company_name}}",
                "body_html": (
                    "<p>Hi {{contact_first_name}},</p>"
                    "<p>Just following up on my previous email. I understand you're busy.</p>"
                    f"<p>I'd love to share how {product} could help {{{{company_name}}}}. "
                    "Would 15 minutes work sometime this week?</p>"
                    "<p>Best,</p>{{signature}}"
                ),
            },
        ],
        3: None,  # Will extend from 2
        4: None,  # Will extend from 2
        5: None,
        6: None,
    }

    base = templates[2][:]

    if num_steps >= 3:
        base.append({
            "step_order": 3, "step_type": "email", "delay_days": 5, "delay_hours": 0,
            "subject": "Thought this might help, {{contact_first_name}}",
            "body_html": (
                "<p>Hi {{contact_first_name}},</p>"
                f"<p>I wanted to share a quick insight about {product} that might be relevant "
                "for {{company_name}}.</p>"
                "<p>Companies in your industry typically see significant improvements when they "
                f"leverage {product}. Happy to walk you through some examples.</p>"
                "<p>Best,</p>{{signature}}"
            ),
        })

    if num_steps >= 4:
        base.append({
            "step_order": 4, "step_type": "email", "delay_days": 7, "delay_hours": 0,
            "subject": "Last note from me, {{contact_first_name}}",
            "body_html": (
                "<p>Hi {{contact_first_name}},</p>"
                "<p>I've reached out a few times and I don't want to be a bother.</p>"
                f"<p>If {product} isn't a priority for {{{{company_name}}}} right now, "
                "no worries at all. But if timing changes, I'm here to help.</p>"
                "<p>Wishing you all the best,</p>{{signature}}"
            ),
        })

    if num_steps >= 5:
        base.insert(3, {
            "step_order": 4, "step_type": "email", "delay_days": 5, "delay_hours": 0,
            "subject": "{{contact_first_name}}, quick case study",
            "body_html": (
                "<p>Hi {{contact_first_name}},</p>"
                f"<p>Wanted to share a quick case study about how a company similar to "
                f"{{{{company_name}}}} used {product} to achieve their goals.</p>"
                "<p>Would you like me to send it over?</p>"
                "<p>Best,</p>{{signature}}"
            ),
        })

    if num_steps >= 6:
        base.insert(4, {
            "step_order": 5, "step_type": "email", "delay_days": 4, "delay_hours": 0,
            "subject": "One more thought for {{company_name}}",
            "body_html": (
                "<p>Hi {{contact_first_name}},</p>"
                "<p>I realize I may not have explained the value clearly enough.</p>"
                f"<p>The main reason companies choose {product} is to save time and "
                "focus on what matters most. Would a brief demo be helpful?</p>"
                "<p>Best,</p>{{signature}}"
            ),
        })

    # Re-number steps
    for i, step in enumerate(base[:num_steps]):
        step["step_order"] = i + 1

    return base[:num_steps]
