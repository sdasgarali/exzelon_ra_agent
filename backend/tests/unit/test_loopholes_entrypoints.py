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
