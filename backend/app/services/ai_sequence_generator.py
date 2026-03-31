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

    Returns:
        List of step dicts: [{step_order, step_type, subject, body_html, delay_days, delay_hours}]
    """
    num_steps = max(2, min(6, num_steps))

    if db is not None:
        try:
            return _generate_with_ai(goal, product, tone, num_steps, db, tenant_id)
        except Exception as e:
            logger.warning("AI sequence generation failed, using template fallback", error=str(e))

    return _generate_template_based(goal, product, tone, num_steps)


def _generate_with_ai(
    goal: str,
    product: str,
    tone: str,
    num_steps: int,
    db: Session,
    tenant_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Use AI adapter to generate email sequence."""
    from app.services.adapters.ai_content import get_ai_adapter
    from app.services.adapters.ai.prompts import OUTREACH_SYSTEM_PROMPT

    adapter = get_ai_adapter(db, tenant_id=tenant_id)
    if adapter is None:
        raise RuntimeError("No AI adapter configured")

    prompt = f"""Create a {num_steps}-step cold email sequence for a staffing/recruitment agency.

**Campaign Goal:** {goal}
**Product/Service:** {product}
**Tone:** {tone}
**Steps:** {num_steps}

For each step, return a JSON array of objects with:
- "step_order": 1-based integer
- "step_type": "email" for email steps
- "subject": email subject line (use {{{{contact_first_name}}}} and {{{{company_name}}}} placeholders)
- "body_html": HTML email body with <p> tags and placeholders ({{{{contact_first_name}}}}, {{{{company_name}}}}, {{{{contact_title}}}}, {{{{signature}}}})
- "delay_days": days to wait before this step (0 for first, 3 for second, 7 for third, 14 for break-up)
- "delay_hours": additional hours (0 for most)

Rules:
- First email: introduce the value proposition tied to their hiring needs
- Follow-ups: completely different angles, do NOT reference previous emails
- Last email: break-up style, gracious, leave the door open
- Keep each email under 120 words
- Short paragraphs (1-2 sentences each)
- No hype, no fluff, no exclamation marks
- Plain, direct, human-sounding
- CTA should be easy and low-pressure

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
