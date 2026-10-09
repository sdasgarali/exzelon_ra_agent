"""Tests for the AI Copilot endpoints (chat, history, clear) and its system prompt."""
from unittest.mock import patch

import pytest

from app.core.security import create_access_token, get_password_hash
from app.db.models.copilot_message import CopilotMessage
from app.db.models.tenant import Tenant, TenantPlan
from app.db.models.user import User, UserRole
from app.services.copilot_knowledge import (
    FEATURE_CATALOG, build_system_prompt, catalog_for_role,
)

CHAT = "/api/v1/copilot/chat"
HISTORY = "/api/v1/copilot/history"
ADAPTER_PATH = "app.api.endpoints.copilot.get_ai_adapter"


class FakeAdapter:
    """Records every prompt it receives and answers with a canned reply."""

    def __init__(self, reply="Use Campaigns (/dashboard/campaigns).", error=None):
        self.reply = reply
        self.error = error
        self.calls = []

    def _call_api(self, messages, max_tokens=None, **kwargs):
        self.calls.append({"messages": messages, "max_tokens": max_tokens})
        if self.error:
            raise self.error
        return self.reply


@pytest.fixture
def fake_adapter():
    adapter = FakeAdapter()
    with patch(ADAPTER_PATH, return_value=adapter) as mocked:
        adapter.factory = mocked
        yield adapter


def _make_user(db, email, role, tenant_id):
    user = User(
        email=email, password_hash=get_password_hash("testpassword"),
        full_name=email, role=role, is_active=True, is_verified=True, tenant_id=tenant_id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_access_token(data={
        "sub": user.email, "role": user.role, "tenant_id": user.tenant_id, "plan": "enterprise",
    })
    return user, {"Authorization": f"Bearer {token}"}


@pytest.fixture
def other_tenant(db_session):
    tenant = Tenant(
        name="Other Org", slug="other-org", plan=TenantPlan.ENTERPRISE,
        max_users=999, max_mailboxes=999, max_contacts=999999, max_campaigns=999, max_leads=999999,
    )
    db_session.add(tenant)
    db_session.commit()
    db_session.refresh(tenant)
    return tenant


def _system_prompt(adapter, call=-1):
    msgs = adapter.calls[call]["messages"]
    assert msgs[0]["role"] == "system"
    return msgs[0]["content"]


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

class TestCopilotChat:
    def test_503_when_ai_not_configured(self, client, auth_headers, db_session):
        with patch(ADAPTER_PATH, return_value=None):
            r = client.post(CHAT, json={"message": "hi"}, headers=auth_headers)
        assert r.status_code == 503
        assert "not configured" in r.json()["detail"]
        assert db_session.query(CopilotMessage).count() == 0

    def test_requires_auth(self, client, fake_adapter):
        r = client.post(CHAT, json={"message": "hi"})
        assert r.status_code in (401, 403)

    def test_success_persists_both_turns(self, client, auth_headers, admin_user, db_session, fake_adapter):
        r = client.post(CHAT, json={"message": "How do I start a campaign?", "context": "leads"},
                        headers=auth_headers)
        assert r.status_code == 200, r.text
        assert r.json() == {"response": fake_adapter.reply}

        rows = db_session.query(CopilotMessage).order_by(CopilotMessage.id).all()
        assert [(m.role, m.content) for m in rows] == [
            ("user", "How do I start a campaign?"),
            ("assistant", fake_adapter.reply),
        ]
        assert all(m.tenant_id == admin_user.tenant_id and m.user_id == admin_user.user_id for m in rows)
        assert all(m.context_page == "leads" for m in rows)
        assert fake_adapter.calls[0]["max_tokens"] == 800
        assert fake_adapter.calls[0]["messages"][-1] == {"role": "user", "content": "How do I start a campaign?"}

    def test_adapter_called_with_effective_tenant(self, client, auth_headers, admin_user, fake_adapter):
        client.post(CHAT, json={"message": "hi"}, headers=auth_headers)
        _, kwargs = fake_adapter.factory.call_args
        assert kwargs.get("tenant_id") == admin_user.tenant_id

    def test_super_admin_impersonation_passes_header_tenant(
        self, client, sa_headers, super_admin_user, test_tenant, db_session, fake_adapter,
    ):
        headers = {**sa_headers, "X-Tenant-ID": str(test_tenant.tenant_id)}
        r = client.post(CHAT, json={"message": "hi"}, headers=headers)
        assert r.status_code == 200
        _, kwargs = fake_adapter.factory.call_args
        assert kwargs.get("tenant_id") == test_tenant.tenant_id
        rows = db_session.query(CopilotMessage).all()
        assert len(rows) == 2 and all(m.tenant_id == test_tenant.tenant_id for m in rows)

    def test_super_admin_without_tenant_persists_under_null_tenant(
        self, client, sa_headers, super_admin_user, test_tenant, db_session, fake_adapter,
    ):
        r = client.post(CHAT, json={"message": "hi"}, headers=sa_headers)
        assert r.status_code == 200
        assert r.json()["response"] == fake_adapter.reply
        _, kwargs = fake_adapter.factory.call_args
        assert kwargs.get("tenant_id") is None
        rows = db_session.query(CopilotMessage).all()
        assert len(rows) == 2
        assert all(m.tenant_id is None and m.user_id == super_admin_user.user_id for m in rows)
        # Remembered across requests ("All Tenants" view).
        h = client.get(HISTORY, headers=sa_headers)
        assert [m["content"] for m in h.json()["messages"]] == ["hi", fake_adapter.reply]
        # Kept separate from the same user's conversation inside a workspace.
        in_tenant = {**sa_headers, "X-Tenant-ID": str(test_tenant.tenant_id)}
        assert client.get(HISTORY, headers=in_tenant).json() == {"messages": []}
        assert client.delete(HISTORY, headers=in_tenant).json() == {"deleted": 0}
        assert client.delete(HISTORY, headers=sa_headers).json() == {"deleted": 2}

    def test_history_is_sent_to_provider(self, client, auth_headers, fake_adapter):
        client.post(CHAT, json={"message": "first question"}, headers=auth_headers)
        client.post(CHAT, json={"message": "second question"}, headers=auth_headers)
        msgs = fake_adapter.calls[1]["messages"]
        assert [m["role"] for m in msgs] == ["system", "user", "assistant", "user"]
        assert msgs[1]["content"] == "first question"
        assert msgs[-1]["content"] == "second question"

    def test_legacy_messages_body_uses_last_user_message(self, client, auth_headers, db_session, fake_adapter):
        body = {"messages": [
            {"role": "user", "content": "old"},
            {"role": "assistant", "content": "answer"},
            {"role": "user", "content": "latest question"},
        ], "context": "inbox"}
        r = client.post(CHAT, json=body, headers=auth_headers)
        assert r.status_code == 200, r.text
        assert fake_adapter.calls[0]["messages"][-1]["content"] == "latest question"
        # Client-sent history is ignored; only system + the new user turn.
        assert len(fake_adapter.calls[0]["messages"]) == 2
        users = db_session.query(CopilotMessage).filter(CopilotMessage.role == "user").all()
        assert [m.content for m in users] == ["latest question"]

    def test_provider_error_returns_502_and_persists_nothing(self, client, auth_headers, db_session):
        adapter = FakeAdapter(error=RuntimeError("boom sk-secret-key-123"))
        with patch(ADAPTER_PATH, return_value=adapter):
            r = client.post(CHAT, json={"message": "hi"}, headers=auth_headers)
        assert r.status_code == 502
        assert r.json()["detail"] == "AI provider error — please try again"
        assert "sk-secret" not in r.text
        assert db_session.query(CopilotMessage).count() == 0

    def test_empty_provider_reply_is_502(self, client, auth_headers, db_session):
        with patch(ADAPTER_PATH, return_value=FakeAdapter(reply="")):
            r = client.post(CHAT, json={"message": "hi"}, headers=auth_headers)
        assert r.status_code == 502
        assert db_session.query(CopilotMessage).count() == 0

    @pytest.mark.parametrize("body", [
        {"message": ""},
        {"message": "   "},
        {"message": "x" * 4001},
        {},
        {"messages": []},
        {"messages": [{"role": "assistant", "content": "no user turn"}]},
        {"messages": [{"role": "user", "content": "y" * 4001}]},
    ])
    def test_message_validation_422(self, client, auth_headers, fake_adapter, body):
        r = client.post(CHAT, json=body, headers=auth_headers)
        assert r.status_code == 422
        assert fake_adapter.calls == []

    def test_max_length_message_accepted(self, client, auth_headers, fake_adapter):
        r = client.post(CHAT, json={"message": "x" * 4000}, headers=auth_headers)
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# History & isolation
# ---------------------------------------------------------------------------

class TestCopilotHistory:
    def test_history_oldest_to_newest(self, client, auth_headers, fake_adapter):
        for q in ("one", "two", "three"):
            client.post(CHAT, json={"message": q}, headers=auth_headers)
        r = client.get(HISTORY, headers=auth_headers)
        assert r.status_code == 200
        msgs = r.json()["messages"]
        assert [m["content"] for m in msgs if m["role"] == "user"] == ["one", "two", "three"]
        assert [m["role"] for m in msgs] == ["user", "assistant"] * 3
        assert set(msgs[0]) == {"id", "role", "content", "context_page", "created_at"}

    def test_history_limit_returns_most_recent(self, client, auth_headers, fake_adapter):
        for q in ("one", "two", "three"):
            client.post(CHAT, json={"message": q}, headers=auth_headers)
        msgs = client.get(HISTORY, params={"limit": 2}, headers=auth_headers).json()["messages"]
        assert [m["role"] for m in msgs] == ["user", "assistant"]
        assert msgs[0]["content"] == "three"

    def test_history_limit_validation(self, client, auth_headers):
        assert client.get(HISTORY, params={"limit": 0}, headers=auth_headers).status_code == 422
        assert client.get(HISTORY, params={"limit": 1000}, headers=auth_headers).status_code == 422

    def test_isolation_between_users_same_tenant(
        self, client, auth_headers, operator_headers, fake_adapter,
    ):
        client.post(CHAT, json={"message": "admin secret"}, headers=auth_headers)
        client.post(CHAT, json={"message": "bdm question"}, headers=operator_headers)

        admin_msgs = client.get(HISTORY, headers=auth_headers).json()["messages"]
        bdm_msgs = client.get(HISTORY, headers=operator_headers).json()["messages"]
        assert [m["content"] for m in admin_msgs if m["role"] == "user"] == ["admin secret"]
        assert [m["content"] for m in bdm_msgs if m["role"] == "user"] == ["bdm question"]

        # The BDM's prompt history must not contain the admin's turns.
        prompt_contents = [m["content"] for m in fake_adapter.calls[1]["messages"]]
        assert "admin secret" not in prompt_contents

    def test_isolation_between_tenants(
        self, client, auth_headers, db_session, other_tenant, fake_adapter,
    ):
        _, other_headers = _make_user(db_session, "admin@other.com", UserRole.ADMIN, other_tenant.tenant_id)
        client.post(CHAT, json={"message": "tenant A"}, headers=auth_headers)
        client.post(CHAT, json={"message": "tenant B"}, headers=other_headers)

        a = client.get(HISTORY, headers=auth_headers).json()["messages"]
        b = client.get(HISTORY, headers=other_headers).json()["messages"]
        assert [m["content"] for m in a if m["role"] == "user"] == ["tenant A"]
        assert [m["content"] for m in b if m["role"] == "user"] == ["tenant B"]

    def test_delete_clears_only_own(
        self, client, auth_headers, operator_headers, db_session, other_tenant, admin_user, fake_adapter,
    ):
        _, other_headers = _make_user(db_session, "admin@other.com", UserRole.ADMIN, other_tenant.tenant_id)
        client.post(CHAT, json={"message": "mine"}, headers=auth_headers)
        client.post(CHAT, json={"message": "teammate"}, headers=operator_headers)
        client.post(CHAT, json={"message": "other tenant"}, headers=other_headers)

        r = client.delete(HISTORY, headers=auth_headers)
        assert r.status_code == 200
        assert r.json() == {"deleted": 2}
        assert client.get(HISTORY, headers=auth_headers).json()["messages"] == []
        assert len(client.get(HISTORY, headers=operator_headers).json()["messages"]) == 2
        assert len(client.get(HISTORY, headers=other_headers).json()["messages"]) == 2
        assert db_session.query(CopilotMessage).filter(
            CopilotMessage.user_id == admin_user.user_id).count() == 0


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

class TestCopilotSystemPrompt:
    def test_prompt_has_scope_refusal_and_routes(self, client, auth_headers, fake_adapter):
        client.post(CHAT, json={"message": "hi", "context": "campaigns"}, headers=auth_headers)
        prompt = _system_prompt(fake_adapter)
        assert "Refusal rule" in prompt
        assert "outside that scope" in prompt
        assert "system prompt" in prompt  # refuses to reveal it
        assert "other workspace" in prompt
        for route in ("/dashboard/campaigns", "/dashboard/mailboxes", "/dashboard/warmup",
                      "/dashboard/billing", "/dashboard/settings"):
            assert route in prompt
        assert '"campaigns" page' in prompt
        assert "/documentation" in prompt

    def test_recruiter_prompt_excludes_restricted_pages(self, client, viewer_headers, fake_adapter):
        client.post(CHAT, json={"message": "hi"}, headers=viewer_headers)
        prompt = _system_prompt(fake_adapter)
        assert "role: recruiter" in prompt
        assert "/dashboard/leads" in prompt
        assert "/dashboard/contacts" in prompt
        for route in ("/dashboard/tenants", "/dashboard/activity-log", "/dashboard/roles",
                      "/dashboard/campaigns", "/dashboard/settings", "/dashboard/users"):
            assert f"({route})" not in prompt, route

    def test_admin_prompt_excludes_super_admin_pages(self, client, auth_headers, fake_adapter):
        client.post(CHAT, json={"message": "hi"}, headers=auth_headers)
        prompt = _system_prompt(fake_adapter)
        assert "(/dashboard/tenants)" not in prompt
        assert "(/dashboard/activity-log)" not in prompt
        assert "(/dashboard/users)" in prompt

    def test_prompt_uses_live_business_rules(self, client, auth_headers, admin_user, db_session, fake_adapter):
        from app.core.settings_resolver import set_tenant_setting
        set_tenant_setting(db_session, "daily_send_limit", 17, tenant_id=admin_user.tenant_id)
        set_tenant_setting(db_session, "cooldown_days", 13, tenant_id=admin_user.tenant_id)
        db_session.commit()
        client.post(CHAT, json={"message": "hi"}, headers=auth_headers)
        prompt = _system_prompt(fake_adapter)
        assert "Daily send limit per mailbox: 17" in prompt
        assert "same contact: 13 days" in prompt

    def test_free_plan_gets_upgrade_notes(self, client, db_session, fake_adapter):
        free = Tenant(name="Free Org", slug="free-org", plan=TenantPlan.STARTER)
        db_session.add(free)
        db_session.commit()
        _, headers = _make_user(db_session, "admin@free.com", UserRole.ADMIN, free.tenant_id)
        r = client.post(CHAT, json={"message": "hi"}, headers=headers)
        assert r.status_code == 200
        prompt = _system_prompt(fake_adapter)
        warmup_line = next(l for l in prompt.splitlines() if "(/dashboard/warmup)" in l)
        assert "NOT on the user's current plan" in warmup_line
        assert "/dashboard/billing" in warmup_line


class TestCopilotKnowledgeUnit:
    def test_catalog_routes_unique_and_dashboard_scoped(self):
        routes = [e.route for e in FEATURE_CATALOG]
        assert len(routes) == len(set(routes))
        assert all(r.startswith("/dashboard") for r in routes)

    def test_unknown_role_falls_back_to_recruiter(self):
        assert catalog_for_role("some_custom") == catalog_for_role("recruiter")

    def test_super_admin_without_plan_has_no_upgrade_notes(self):
        prompt = build_system_prompt(
            stats={}, context_page="", user_role="super_admin", plan_features=None,
            business_rules={"daily_send_limit": 30, "cooldown_days": 10,
                            "max_contacts_per_company_job": 2, "min_salary_threshold": 40000,
                            "complaint_rate_threshold": 0.003},
        )
        assert "/dashboard/tenants" in prompt
        assert "NOT on the user's current plan" not in prompt
        assert "0.3%" in prompt
        assert "$40,000" in prompt
