"""Regression tests for the entry-point loopholes closed in Plan_Credit_Loopholes.md (Agent B).

Each test reproduces an abuse path that was open on decc862 and asserts it is now
blocked. Grouped by plan item (B1..B8).
"""
import json

import pytest

from app.db.models.settings import Settings
from app.db.models.tenant_settings import TenantSettings

pytestmark = pytest.mark.unit

API = "/api/v1"


def _tenant_value(db_session, tenant_id, key):
    row = db_session.query(TenantSettings).filter(
        TenantSettings.tenant_id == tenant_id, TenantSettings.key == key,
    ).first()
    return None if row is None else json.loads(row.value_json)


@pytest.fixture
def admin_full_settings(db_session):
    """Give tenant admins full access to every settings tab (as production does),
    so the tests exercise the new guards rather than the tab-permission check."""
    db_session.add(Settings(key="role_permissions", type="json", value_json=json.dumps({
        "admin": {"settings": "full"}, "bdm": {"settings": "read"}, "recruiter": {"settings": "no_access"},
    })))
    db_session.commit()


# ---------------------------------------------------------------------------
# B1 — PUT /settings/{key}: platform-controlled keys + safe business-rule ranges
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("admin_full_settings")
class TestB1SettingsLockdown:

    @pytest.mark.parametrize("key,value", [
        ("credit_enforcement_enabled", False),
        ("feature_email_validation_enabled", False),
        ("feature_campaigns_enabled", True),
        ("feature_outreach_enabled", True),
        ("credit_anything", 1),
        ("ai_provider", "anthropic"),
        ("ai_model", "claude-opus"),
        ("warmup_ai_provider", "openai"),
        ("openai_api_key", "sk-x"),
        ("groq_api_key", "gsk-x"),
    ])
    def test_tenant_admin_cannot_set_platform_keys(self, client, db_session, auth_headers, test_tenant, key, value):
        r = client.put(f"{API}/settings/{key}", headers=auth_headers, json={"value": value})
        assert r.status_code == 403, r.text
        assert _tenant_value(db_session, test_tenant.tenant_id, key) is None

    def test_super_admin_can_set_platform_key_for_tenant(self, client, db_session, sa_headers, test_tenant):
        headers = {**sa_headers, "X-Tenant-ID": str(test_tenant.tenant_id)}
        r = client.put(f"{API}/settings/feature_campaigns_enabled", headers=headers, json={"value": False})
        assert r.status_code == 200, r.text
        assert _tenant_value(db_session, test_tenant.tenant_id, "feature_campaigns_enabled") is False

    def test_tenant_admin_cannot_clear_platform_override(self, client, db_session, auth_headers, test_tenant):
        # Super admin disabled campaigns for this tenant; deleting the override
        # would fall back to the global default (enabled).
        db_session.add(TenantSettings(tenant_id=test_tenant.tenant_id, key="feature_campaigns_enabled",
                                      value_json=json.dumps(False)))
        db_session.commit()
        r = client.delete(f"{API}/settings/feature_campaigns_enabled/tenant-override", headers=auth_headers)
        assert r.status_code == 403, r.text
        assert _tenant_value(db_session, test_tenant.tenant_id, "feature_campaigns_enabled") is False

    @pytest.mark.parametrize("key,value", [
        ("cooldown_days", 0),
        ("cooldown_days", -5),
        ("cooldown_days", 366),
        ("max_contacts_per_company_job", 999),
        ("max_contacts_per_company_job", 0),
        ("daily_send_limit", 10_000),
        ("daily_send_limit", 0),
        ("cooldown_days", "abc"),
    ])
    def test_tenant_admin_business_rules_out_of_range_rejected(self, client, db_session, auth_headers, test_tenant, key, value):
        r = client.put(f"{API}/settings/{key}", headers=auth_headers, json={"value": value})
        assert r.status_code == 400, r.text
        assert _tenant_value(db_session, test_tenant.tenant_id, key) is None

    @pytest.mark.parametrize("key,value", [
        ("cooldown_days", 14),
        ("max_contacts_per_company_job", 1),
        ("daily_send_limit", 25),
    ])
    def test_tenant_admin_business_rules_in_range_accepted(self, client, db_session, auth_headers, test_tenant, key, value):
        r = client.put(f"{API}/settings/{key}", headers=auth_headers, json={"value": value})
        assert r.status_code == 200, r.text
        assert _tenant_value(db_session, test_tenant.tenant_id, key) == value

    def test_value_json_path_is_validated_too(self, client, auth_headers):
        r = client.put(f"{API}/settings/cooldown_days", headers=auth_headers, json={"value_json": "0"})
        assert r.status_code == 400

    def test_super_admin_global_business_rule_not_range_limited(self, client, sa_headers):
        r = client.put(f"{API}/settings/daily_send_limit", headers=sa_headers, json={"value": 100})
        assert r.status_code == 200, r.text

    def test_write_scoped_api_key_cannot_write_settings(self):
        from app.core.api_key_scopes import check_scope
        assert check_scope(["write"], "PUT", "/api/v1/settings/cooldown_days")[0] is False
        assert check_scope(["admin"], "PUT", "/api/v1/settings/cooldown_days")[0] is True


# ---------------------------------------------------------------------------
# B2 — is_test / validation_status are super-admin-only on contacts
# ---------------------------------------------------------------------------

def _make_contact(db_session, tenant_id, email="b2@acme-corp.com", **kw):
    from app.db.models.contact import ContactDetails
    c = ContactDetails(tenant_id=tenant_id, client_name="Acme", first_name="Ann",
                       last_name="Lee", email=email, **kw)
    db_session.add(c)
    db_session.commit()
    db_session.refresh(c)
    return c


class TestB2ContactBypassFields:

    def test_admin_cannot_create_test_contact(self, client, auth_headers):
        r = client.post(f"{API}/contacts", headers=auth_headers, json={
            "client_name": "Acme", "first_name": "A", "last_name": "B",
            "email": "t1@acme-corp.com", "is_test": True})
        assert r.status_code == 403, r.text

    def test_bdm_cannot_create_test_contact(self, client, operator_headers):
        r = client.post(f"{API}/contacts", headers=operator_headers, json={
            "client_name": "Acme", "first_name": "A", "last_name": "B",
            "email": "t2@acme-corp.com", "is_test": True})
        assert r.status_code == 403, r.text

    def test_admin_can_create_normal_contact(self, client, auth_headers):
        r = client.post(f"{API}/contacts", headers=auth_headers, json={
            "client_name": "Acme", "first_name": "A", "last_name": "B",
            "email": "t3@acme-corp.com", "is_test": False})
        assert r.status_code == 201, r.text
        assert r.json()["is_test"] is False

    def test_admin_cannot_flip_is_test(self, client, db_session, auth_headers, test_tenant):
        c = _make_contact(db_session, test_tenant.tenant_id)
        r = client.put(f"{API}/contacts/{c.contact_id}", headers=auth_headers, json={"is_test": True})
        assert r.status_code == 403, r.text
        db_session.refresh(c)
        assert c.is_test is False

    def test_admin_cannot_mark_contact_valid(self, client, db_session, auth_headers, test_tenant):
        c = _make_contact(db_session, test_tenant.tenant_id, validation_status=None)
        r = client.put(f"{API}/contacts/{c.contact_id}", headers=auth_headers,
                       json={"validation_status": "valid"})
        assert r.status_code == 403, r.text
        db_session.refresh(c)
        assert c.validation_status is None

    def test_admin_echoing_unchanged_values_is_allowed(self, client, db_session, auth_headers, test_tenant):
        c = _make_contact(db_session, test_tenant.tenant_id, validation_status="valid")
        r = client.put(f"{API}/contacts/{c.contact_id}", headers=auth_headers,
                       json={"title": "HR Director", "is_test": False, "validation_status": "valid"})
        assert r.status_code == 200, r.text
        assert r.json()["title"] == "HR Director"

    def test_admin_email_change_cannot_carry_valid_status(self, client, db_session, auth_headers, test_tenant):
        c = _make_contact(db_session, test_tenant.tenant_id, validation_status="valid")
        r = client.put(f"{API}/contacts/{c.contact_id}", headers=auth_headers,
                       json={"email": "other@acme-corp.com", "validation_status": "valid"})
        assert r.status_code == 200, r.text
        assert r.json()["validation_status"] is None

    def test_super_admin_can_set_bypass_fields(self, client, db_session, sa_headers, test_tenant):
        c = _make_contact(db_session, test_tenant.tenant_id)
        r = client.put(f"{API}/contacts/{c.contact_id}", headers=sa_headers,
                       json={"is_test": True, "validation_status": "valid"})
        assert r.status_code == 200, r.text
        assert r.json()["is_test"] is True and r.json()["validation_status"] == "valid"


# ---------------------------------------------------------------------------
# B3 — /leads/database-search is budget-gated and metered
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_apollo(monkeypatch):
    calls = []

    class _FakeApollo:
        def __init__(self, *a, **k):
            pass

        def search_contacts(self, company_name, job_title=None, state=None, limit=25, **k):
            calls.append(limit)
            return [{"first_name": f"P{i}", "last_name": "X", "email": f"p{i}@acme-corp.com"}
                    for i in range(min(limit, 4))]

    import app.services.adapters.contact_discovery.apollo as apollo_mod
    monkeypatch.setattr(apollo_mod, "ApolloAdapter", _FakeApollo)
    return calls


class TestB3DatabaseSearch:

    def test_results_are_metered_and_committed(self, client, db_session, auth_headers, test_tenant, fake_apollo):
        from app.db.models.credit_usage import CreditUsage
        from app.core.credit_costs import cost_for
        r = client.post(f"{API}/leads/database-search", headers=auth_headers,
                        json={"company": "Acme Manufacturing", "job_title": "HR Manager", "limit": 10})
        assert r.status_code == 200, r.text
        assert r.json()["count"] == 4
        db_session.expire_all()
        rows = db_session.query(CreditUsage).filter(
            CreditUsage.tenant_id == test_tenant.tenant_id,
            CreditUsage.usage_type == "contact_enriched",
        ).all()
        assert len(rows) == 1
        assert rows[0].credits_used == pytest.approx(cost_for("contact_enriched", 4))

    def test_budget_gate_uses_worst_case_and_blocks(self, client, auth_headers, fake_apollo, monkeypatch):
        from fastapi import HTTPException
        import app.services.credit_metering as cm
        seen = {}

        def _deny(db, tenant_id, plan=None, credits_needed=1.0):
            seen["needed"] = credits_needed
            raise HTTPException(status_code=402, detail="Out of credits")

        monkeypatch.setattr(cm, "check_credit_budget", _deny)
        r = client.post(f"{API}/leads/database-search", headers=auth_headers,
                        json={"company": "Acme Manufacturing", "limit": 20})
        assert r.status_code == 402
        from app.core.credit_costs import cost_for
        assert seen["needed"] == pytest.approx(20 * cost_for("contact_enriched"))
        assert fake_apollo == []  # provider never called

    def test_suspended_tenant_blocked(self, client, db_session, auth_headers, test_tenant, fake_apollo):
        test_tenant.billing_suspended = True
        db_session.commit()
        r = client.post(f"{API}/leads/database-search", headers=auth_headers,
                        json={"company": "Acme Manufacturing"})
        assert r.status_code == 402
        assert fake_apollo == []

    def test_super_admin_without_tenant_is_not_metered(self, client, db_session, sa_headers, fake_apollo):
        from app.db.models.credit_usage import CreditUsage
        r = client.post(f"{API}/leads/database-search", headers=sa_headers,
                        json={"company": "Acme Manufacturing", "limit": 5})
        assert r.status_code == 200, r.text
        assert db_session.query(CreditUsage).count() == 0

    def test_read_scoped_api_key_cannot_call_it(self):
        from app.core.api_key_scopes import check_scope
        assert check_scope(["read"], "POST", "/api/v1/leads/database-search")[0] is False
