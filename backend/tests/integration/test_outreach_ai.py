"""Integration tests for AI outreach drafting in the pipeline."""
import pytest
from unittest.mock import patch, MagicMock

from app.services.adapters.ai.prompts import (
    OUTREACH_SYSTEM_PROMPT,
    build_outreach_user_prompt,
    parse_ai_email_response,
)


# ---------- Prompt module tests ----------

@pytest.mark.integration
def test_system_prompt_has_anti_patterns():
    """System prompt contains key anti-pattern rules."""
    assert "I hope this finds you well" in OUTREACH_SYSTEM_PROMPT
    assert "synergy" in OUTREACH_SYSTEM_PROMPT
    assert "Under 120 words" in OUTREACH_SYSTEM_PROMPT


@pytest.mark.integration
def test_build_prompt_step_1():
    """Step 1 prompt includes recipient and company context."""
    prompt = build_outreach_user_prompt(
        contact_name="John",
        contact_title="HR Director",
        company_name="Acme Corp",
        job_title="Warehouse Supervisor",
        context={"industry": "Manufacturing", "location": "Dallas, TX"},
        step_number=1,
    )
    assert "John" in prompt
    assert "Acme Corp" in prompt
    assert "Warehouse Supervisor" in prompt
    assert "Manufacturing" in prompt
    assert "SUBJECT:" in prompt


@pytest.mark.integration
def test_build_prompt_step_2_follow_up():
    """Step 2 prompt instructs short follow-up."""
    prompt = build_outreach_user_prompt(
        contact_name="Jane",
        contact_title="VP Operations",
        company_name="BigCo",
        job_title="Forklift Operator",
        step_number=2,
    )
    assert "Under 80 words" in prompt
    assert "different angle" in prompt.lower()


@pytest.mark.integration
def test_build_prompt_step_4_breakup():
    """Step 4+ prompt instructs break-up email."""
    prompt = build_outreach_user_prompt(
        contact_name="Bob",
        contact_title="Plant Manager",
        company_name="FactoryCo",
        job_title="Machine Operator",
        step_number=4,
    )
    assert "break-up" in prompt.lower()
    assert "50 words" in prompt.lower()


@pytest.mark.integration
def test_parse_ai_response_success():
    """Parse a well-formed AI response."""
    text = "SUBJECT: Quick question about staffing\n---\n<p>Hi John,</p><p>Test body.</p>\n---\nHi John,\n\nTest body."
    result = parse_ai_email_response(text, "John", "Warehouse Supervisor")
    assert result["subject"] == "Quick question about staffing"
    assert "<p>" in result["body_html"]
    assert "Hi John" in result["body_text"]


@pytest.mark.integration
def test_parse_ai_response_fallback():
    """Parse failure returns safe fallback."""
    result = parse_ai_email_response("", "John", "Warehouse Supervisor")
    assert "Warehouse Supervisor" in result["subject"]
    assert "<p>" in result["body_html"]


# ---------- Pipeline wiring tests ----------

@pytest.mark.integration
@patch("app.services.outreach_draft_service.get_ai_adapter")
@patch("app.services.outreach_draft_service.get_tenant_setting_bool")
def test_fallback_used_when_ai_disabled(mock_toggle, mock_adapter):
    """When AI drafting is off, draft_outreach_email returns None → pipeline uses hardcoded."""
    from app.services.outreach_draft_service import draft_outreach_email

    mock_toggle.return_value = False
    contact = MagicMock()
    contact.first_name = "Test"
    contact.email = "t@t.com"
    contact.client_name = "Co"
    contact.tenant_id = 1
    contact.lead_id = None
    contact.title = "Manager"
    contact.location_state = "TX"

    result = draft_outreach_email(MagicMock(), contact, tenant_id=1)
    assert result is None  # Caller will use hardcoded fallback


@pytest.mark.integration
@patch("app.services.outreach_draft_service.get_ai_adapter")
@patch("app.services.outreach_draft_service.get_tenant_setting_bool")
def test_ai_email_used_when_enabled(mock_toggle, mock_get_adapter):
    """When AI drafting is on + adapter available, returns AI content."""
    from app.services.outreach_draft_service import draft_outreach_email

    mock_toggle.return_value = True
    adapter = MagicMock()
    adapter.generate_email.return_value = {
        "subject": "AI Generated Subject",
        "body_html": "<p>AI body</p>",
        "body_text": "AI body",
    }
    adapter.research_company.return_value = {}
    mock_get_adapter.return_value = adapter

    contact = MagicMock()
    contact.first_name = "Test"
    contact.email = "t@t.com"
    contact.client_name = "Co"
    contact.tenant_id = 1
    contact.lead_id = None
    contact.title = "Manager"
    contact.location_state = "TX"

    result = draft_outreach_email(MagicMock(), contact, tenant_id=1)
    assert result is not None
    subject, html, text = result
    assert subject == "AI Generated Subject"


@pytest.mark.integration
@patch("app.services.outreach_draft_service.get_ai_adapter")
@patch("app.services.outreach_draft_service.get_tenant_setting_bool")
def test_fallback_on_ai_failure(mock_toggle, mock_get_adapter):
    """When AI adapter raises, returns None → hardcoded fallback."""
    from app.services.outreach_draft_service import draft_outreach_email

    mock_toggle.return_value = True
    adapter = MagicMock()
    adapter.generate_email.side_effect = Exception("API error")
    adapter.research_company.return_value = {}
    mock_get_adapter.return_value = adapter

    contact = MagicMock()
    contact.first_name = "Test"
    contact.email = "t@t.com"
    contact.client_name = "Co"
    contact.tenant_id = 1
    contact.lead_id = None
    contact.title = "Manager"
    contact.location_state = "TX"

    result = draft_outreach_email(MagicMock(), contact, tenant_id=1)
    assert result is None


@pytest.mark.integration
def test_research_cache_cleared_between_runs():
    """Cache is isolated between pipeline runs."""
    from app.services.outreach_draft_service import _research_cache, clear_research_cache

    _research_cache["TestCo"] = {"industry": "Cached"}
    assert len(_research_cache) == 1

    clear_research_cache()
    assert len(_research_cache) == 0


@pytest.mark.integration
def test_sequence_generator_template_fallback():
    """Sequence generator falls back to templates when no db is passed."""
    from app.services.ai_sequence_generator import generate_sequence

    steps = generate_sequence(
        goal="book meetings",
        product="staffing services",
        tone="professional",
        num_steps=4,
        db=None,  # No DB → template fallback
    )
    assert len(steps) == 4
    assert steps[0]["step_order"] == 1
    assert steps[0]["step_type"] == "email"
    assert "{{contact_first_name}}" in steps[0]["subject"] or "{{company_name}}" in steps[0]["subject"]
