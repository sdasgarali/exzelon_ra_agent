"""AI Sequence Generator — creates multi-step email campaign sequences."""
import json
import structlog
from typing import Dict, Any, List

logger = structlog.get_logger()


def generate_sequence(
    goal: str,
    product: str,
    tone: str = "professional",
    num_steps: int = 4,
) -> List[Dict[str, Any]]:
    """Generate an email sequence using AI.

    Falls back to template-based generation if AI is unavailable.

    Args:
        goal: Campaign goal (e.g., "book meetings", "generate leads")
        product: Product/service being promoted
        tone: Email tone (professional, casual, urgent, friendly)
        num_steps: Number of email steps (2-6)

    Returns:
        List of step dicts: [{step_order, step_type, subject, body_html, delay_days, delay_hours}]
    """
    num_steps = max(2, min(6, num_steps))

    try:
        return _generate_with_ai(goal, product, tone, num_steps)
    except Exception as e:
        logger.warning("AI sequence generation failed, using template fallback", error=str(e))
        return _generate_template_based(goal, product, tone, num_steps)


def _generate_with_ai(goal: str, product: str, tone: str, num_steps: int) -> List[Dict[str, Any]]:
    """Use AI adapter to generate email sequence."""
    from app.services.adapters.ai_content import get_ai_adapter

    prompt = f"""You are an expert cold email copywriter. Create a {num_steps}-step email sequence.

**Campaign Goal:** {goal}
**Product/Service:** {product}
**Tone:** {tone}
**Steps:** {num_steps}

For each step, return a JSON array of objects with:
- "step_order": 1-based integer
- "step_type": "email" for email steps, "wait" for wait steps
- "subject": email subject line (use {{{{contact_first_name}}}} and {{{{company_name}}}} placeholders)
- "body_html": HTML email body with placeholders ({{{{contact_first_name}}}}, {{{{company_name}}}}, {{{{contact_title}}}}, {{{{signature}}}})
- "delay_days": days to wait before this step (0 for first, 2-5 for subsequent)
- "delay_hours": additional hours (0 for most)

Rules:
- First email should be warm and introduce the value proposition
- Follow-ups should reference the previous email
- Include a "break-up" email as the last step
- Keep emails short (3-5 sentences each)
- Use personalization placeholders
- Don't be pushy or salesy

Return ONLY a JSON array, no markdown or other text."""

    adapter = get_ai_adapter()
    response = adapter.generate_content(prompt=prompt, max_tokens=1500)

    text = response.get("content", "") if isinstance(response, dict) else str(response)

    # Extract JSON from response
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]

    steps = json.loads(text.strip())

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
