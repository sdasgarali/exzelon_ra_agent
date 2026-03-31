"""Unit tests for outreach_draft_service.py."""
import pytest
from unittest.mock import patch, MagicMock

from app.services.outreach_draft_service import (
    draft_outreach_email,
    clear_research_cache,
    _gather_context,
    _is_context_thin,
    _research_company_if_needed,
    _research_cache,
)


@pytest.fixture
def mock_contact():
    """Create a mock ContactDetails object."""
    contact = MagicMock()
    contact.contact_id = 1
    contact.tenant_id = 1
    contact.first_name = "John"
    contact.last_name = "Doe"
    contact.title = "HR Director"
    contact.email = "john@acme.com"
    contact.client_name = "Acme Corp"
    contact.location_state = "TX"
    contact.lead_id = 10
    return contact


@pytest.fixture
def mock_lead():
    """Create a mock LeadDetails object."""
    lead = MagicMock()
    lead.lead_id = 10
    lead.job_title = "Warehouse Supervisor"
    lead.client_name = "Acme Corp"
    lead.state = "TX"
    lead.city = "Dallas"
    return lead


@pytest.fixture
def mock_mailbox():
    """Create a mock SenderMailbox object."""
    mb = MagicMock()
    mb.display_name = "Jane Smith"
    mb.email = "jane@exzelon.com"
    mb.email_signature_json = None
    return mb


@pytest.fixture
def mock_adapter():
    """Create a mock AI adapter."""
    adapter = MagicMock()
    adapter.generate_email.return_value = {
        "subject": "Staffing for Warehouse Supervisor",
        "body_html": "<p>Hi John,</p><p>Great content here.</p>",
        "body_text": "Hi John,\n\nGreat content here.",
    }
    adapter.research_company.return_value = {
        "industry": "Manufacturing",
        "description": "Industrial manufacturer",
        "company_size": "201-500",
        "headquarters": "Dallas, TX",
    }
    return adapter


@pytest.fixture(autouse=True)
def _clear_cache():
    """Clear research cache before each test."""
    clear_research_cache()
    yield
    clear_research_cache()


# ---------- _gather_context tests ----------

@pytest.mark.unit
def test_gather_context_contact_only(db_session, mock_contact):
    """Context from contact when no lead or client in DB."""
    mock_contact.lead_id = None
    ctx = _gather_context(db_session, mock_contact, None, None, 1)
    assert ctx["contact_name"] == "John"
    assert ctx["contact_title"] == "HR Director"
    assert ctx["company_name"] == "Acme Corp"


@pytest.mark.unit
def test_gather_context_with_lead(db_session, mock_contact, mock_lead):
    """Lead data enriches context."""
    ctx = _gather_context(db_session, mock_contact, mock_lead, None, 1)
    assert ctx["job_title"] == "Warehouse Supervisor"
    assert ctx["location"] == "Dallas, TX"


@pytest.mark.unit
def test_gather_context_with_mailbox(db_session, mock_contact, mock_mailbox):
    """Mailbox provides sender info."""
    mock_contact.lead_id = None
    ctx = _gather_context(db_session, mock_contact, None, mock_mailbox, 1)
    assert ctx["sender_name"] == "Jane Smith"


@pytest.mark.unit
def test_gather_context_loads_lead_from_fk(db_session, mock_contact):
    """When lead is None but contact.lead_id is set, loads from DB (returns None in test since no real DB lead)."""
    ctx = _gather_context(db_session, mock_contact, None, None, 1)
    # lead_id=10 but no lead in SQLite test DB, so no job_title
    assert ctx.get("job_title", "") == ""


# ---------- _is_context_thin tests ----------

@pytest.mark.unit
def test_is_context_thin_empty():
    assert _is_context_thin({}) is True


@pytest.mark.unit
def test_is_context_thin_with_industry():
    assert _is_context_thin({"industry": "Manufacturing"}) is False


@pytest.mark.unit
def test_is_context_thin_with_description():
    assert _is_context_thin({"description": "A company"}) is False


@pytest.mark.unit
def test_is_context_thin_with_empty_strings():
    assert _is_context_thin({"industry": "", "description": "", "company_size": ""}) is True


# ---------- _research_company_if_needed tests ----------

@pytest.mark.unit
def test_research_cache_miss(mock_adapter):
    """Calls research_company on cache miss."""
    ctx = {"company_name": "NewCo", "industry": "", "description": "", "company_size": ""}
    _research_company_if_needed(mock_adapter, ctx)
    mock_adapter.research_company.assert_called_once()
    assert ctx["industry"] == "Manufacturing"
    # Verify cache was populated
    assert "NewCo" in _research_cache


@pytest.mark.unit
def test_research_cache_hit(mock_adapter):
    """Uses cache on second call — no new API call."""
    _research_cache["CachedCo"] = {"industry": "Logistics", "description": "Shipping"}
    ctx = {"company_name": "CachedCo", "industry": "", "description": "", "company_size": ""}
    _research_company_if_needed(mock_adapter, ctx)
    mock_adapter.research_company.assert_not_called()
    assert ctx["industry"] == "Logistics"


@pytest.mark.unit
def test_research_failure_cached(mock_adapter):
    """Failed research is cached to prevent retries."""
    mock_adapter.research_company.side_effect = Exception("API down")
    ctx = {"company_name": "FailCo", "industry": "", "description": "", "company_size": ""}
    _research_company_if_needed(mock_adapter, ctx)
    assert _research_cache["FailCo"] == {}  # Empty dict cached
    assert ctx["industry"] == ""  # Not enriched


@pytest.mark.unit
def test_research_skipped_when_rich():
    """No research when context already has industry."""
    adapter = MagicMock()
    ctx = {"company_name": "RichCo", "industry": "Healthcare"}
    _research_company_if_needed(adapter, ctx)
    adapter.research_company.assert_not_called()


# ---------- draft_outreach_email tests ----------

@pytest.mark.unit
@patch("app.services.outreach_draft_service.get_ai_adapter")
@patch("app.services.outreach_draft_service.get_tenant_setting_bool")
def test_draft_disabled_returns_none(mock_toggle, mock_get_adapter, db_session, mock_contact):
    """Returns None when ai_outreach_drafting is disabled."""
    mock_toggle.return_value = False
    result = draft_outreach_email(db_session, mock_contact, tenant_id=1)
    assert result is None
    mock_get_adapter.assert_not_called()


@pytest.mark.unit
@patch("app.services.outreach_draft_service.get_ai_adapter")
@patch("app.services.outreach_draft_service.get_tenant_setting_bool")
def test_draft_no_adapter_returns_none(mock_toggle, mock_get_adapter, db_session, mock_contact):
    """Returns None when no AI adapter is configured."""
    mock_toggle.return_value = True
    mock_get_adapter.return_value = None
    result = draft_outreach_email(db_session, mock_contact, tenant_id=1)
    assert result is None


@pytest.mark.unit
@patch("app.services.outreach_draft_service.get_ai_adapter")
@patch("app.services.outreach_draft_service.get_tenant_setting_bool")
def test_draft_success(mock_toggle, mock_get_adapter, db_session, mock_contact, mock_lead, mock_mailbox, mock_adapter):
    """Returns (subject, html, text) on success."""
    mock_toggle.return_value = True
    mock_get_adapter.return_value = mock_adapter
    result = draft_outreach_email(db_session, mock_contact, lead=mock_lead, mailbox=mock_mailbox, tenant_id=1)
    assert result is not None
    subject, body_html, body_text = result
    assert "Staffing" in subject or "Warehouse" in subject
    assert "<p>" in body_html
    assert len(body_text) > 0


@pytest.mark.unit
@patch("app.services.outreach_draft_service.get_ai_adapter")
@patch("app.services.outreach_draft_service.get_tenant_setting_bool")
def test_draft_empty_result_returns_none(mock_toggle, mock_get_adapter, db_session, mock_contact, mock_adapter):
    """Returns None when adapter returns empty result."""
    mock_toggle.return_value = True
    mock_adapter.generate_email.return_value = {"subject": "", "body_html": ""}
    mock_get_adapter.return_value = mock_adapter
    result = draft_outreach_email(db_session, mock_contact, tenant_id=1)
    assert result is None


@pytest.mark.unit
@patch("app.services.outreach_draft_service.get_ai_adapter")
@patch("app.services.outreach_draft_service.get_tenant_setting_bool")
def test_draft_error_result_returns_none(mock_toggle, mock_get_adapter, db_session, mock_contact, mock_adapter):
    """Returns None when adapter returns an error fallback."""
    mock_toggle.return_value = True
    mock_adapter.generate_email.return_value = {
        "subject": "Fallback",
        "body_html": "<p>fallback</p>",
        "error": "API timeout",
    }
    mock_get_adapter.return_value = mock_adapter
    result = draft_outreach_email(db_session, mock_contact, tenant_id=1)
    assert result is None


@pytest.mark.unit
@patch("app.services.outreach_draft_service.get_ai_adapter")
@patch("app.services.outreach_draft_service.get_tenant_setting_bool")
def test_draft_exception_returns_none(mock_toggle, mock_get_adapter, db_session, mock_contact):
    """Returns None on unexpected exception — never raises."""
    mock_toggle.return_value = True
    mock_get_adapter.side_effect = RuntimeError("unexpected")
    result = draft_outreach_email(db_session, mock_contact, tenant_id=1)
    assert result is None


# ---------- clear_research_cache test ----------

@pytest.mark.unit
def test_clear_research_cache():
    _research_cache["SomeCo"] = {"industry": "Test"}
    clear_research_cache()
    assert len(_research_cache) == 0
