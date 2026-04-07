"""Tests for the Agent Context Builder."""
import pytest
from unittest.mock import MagicMock
from datetime import datetime

pytestmark = pytest.mark.unit


class TestBuildContactContext:
    def test_basic_context_with_contact_and_lead(self):
        from app.services.ai_sales_agent.agent_context import build_contact_context

        contact = MagicMock()
        contact.contact_id = 1
        contact.first_name = "John"
        contact.last_name = "Doe"
        contact.email = "john@acme.com"
        contact.title = "HR Director"
        contact.client_name = "Acme Corp"
        contact.priority_level = "P1_JOB_POSTER"
        contact.lead_score = 75
        contact.validation_status = "Valid"
        contact.outreach_status = "ACTIVE"
        contact.phone = None

        lead = MagicMock()
        lead.lead_id = 10
        lead.job_title = "Warehouse Manager"
        lead.state = "TX"
        lead.city = "Houston"
        lead.industry = "Manufacturing"
        lead.company_size = "201-500"
        lead.salary_min = 60000
        lead.employer_linkedin_url = "https://linkedin.com/company/acme"
        lead.employer_website = "https://acme.com"
        lead.posting_date = datetime(2026, 4, 1)
        lead.created_at = datetime(2026, 4, 1)

        ctx = build_contact_context(contact=contact, lead=lead)

        assert ctx["contact"]["name"] == "John Doe"
        assert ctx["contact"]["email"] == "john@acme.com"
        assert ctx["contact"]["title"] == "HR Director"
        assert ctx["lead"]["job_title"] == "Warehouse Manager"
        assert ctx["lead"]["state"] == "TX"
        assert ctx["company"]["name"] == "Acme Corp"
        assert ctx["company"]["industry"] == "Manufacturing"
        assert ctx["company"]["size"] == "201-500"
        assert "scores" in ctx

    def test_context_with_no_lead(self):
        from app.services.ai_sales_agent.agent_context import build_contact_context

        contact = MagicMock()
        contact.contact_id = 2
        contact.first_name = "Jane"
        contact.last_name = "Smith"
        contact.email = "jane@example.com"
        contact.title = "Recruiter"
        contact.client_name = "Example Inc"
        contact.priority_level = "P3_HR_CONTACT"
        contact.lead_score = None
        contact.validation_status = "Valid"
        contact.outreach_status = "ACTIVE"
        contact.phone = None

        ctx = build_contact_context(contact=contact, lead=None)

        assert ctx["contact"]["name"] == "Jane Smith"
        assert ctx["lead"]["job_title"] is None
        assert ctx["company"]["name"] == "Example Inc"

    def test_context_includes_history_when_provided(self):
        from app.services.ai_sales_agent.agent_context import build_contact_context

        contact = MagicMock()
        contact.contact_id = 3
        contact.first_name = "Bob"
        contact.last_name = "Jones"
        contact.email = "bob@test.com"
        contact.title = "VP Ops"
        contact.client_name = "TestCo"
        contact.priority_level = "P2_HIRING_MANAGER"
        contact.lead_score = 50
        contact.validation_status = "Valid"
        contact.outreach_status = "ACTIVE"
        contact.phone = "555-1234"

        history = {
            "emails_sent": 2,
            "emails_replied": 1,
            "last_reply_intent": "question",
            "last_outreach_date": "2026-04-01",
            "objections": ["bad_timing"],
        }

        ctx = build_contact_context(contact=contact, lead=None, history=history)

        assert ctx["history"]["emails_sent"] == 2
        assert ctx["history"]["emails_replied"] == 1
        assert ctx["history"]["last_reply_intent"] == "question"

    def test_context_with_none_contact(self):
        from app.services.ai_sales_agent.agent_context import build_contact_context

        ctx = build_contact_context(contact=None, lead=None)
        assert ctx["contact"]["name"] is None
        assert ctx["contact"]["email"] is None

    def test_context_includes_built_at_timestamp(self):
        from app.services.ai_sales_agent.agent_context import build_contact_context

        contact = MagicMock()
        contact.contact_id = 1
        contact.first_name = "Test"
        contact.last_name = ""
        contact.email = "t@t.com"
        contact.title = ""
        contact.client_name = ""
        contact.priority_level = None
        contact.lead_score = None
        contact.validation_status = "Valid"
        contact.outreach_status = "ACTIVE"
        contact.phone = None

        ctx = build_contact_context(contact=contact)
        assert "built_at" in ctx
        assert "T" in ctx["built_at"]  # ISO format


class TestBuildInteractionHistory:
    def test_returns_dict_with_required_keys(self):
        from app.services.ai_sales_agent.agent_context import build_interaction_history

        db = MagicMock()
        # Make all query chains return 0/None
        db.query.return_value.filter.return_value.count.return_value = 0
        db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None

        history = build_interaction_history(db, contact_id=1, tenant_id=1)

        assert isinstance(history, dict)
        assert "emails_sent" in history
        assert "emails_replied" in history
        assert "last_reply_intent" in history
        assert "objections" in history
