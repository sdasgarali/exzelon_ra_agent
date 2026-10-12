"""A tenant's AI provider/model choice never runs on the platform's paid key.

Tenants may bring their own provider, model and key (settings stay tenant-writable).
`resolve_ai_config` only honours a tenant override when the tenant also supplied its
own key; otherwise the platform configuration is used as a whole.
"""
import json

import pytest

from app.db.models.settings import Settings
from app.db.models.tenant_settings import TenantSettings
from app.services.adapters.ai_content import resolve_ai_config

pytestmark = pytest.mark.unit

API = "/api/v1"


def _global(db, key, value):
    db.add(Settings(key=key, value_json=json.dumps(value)))
    db.commit()


def _tenant(db, tenant_id, key, value):
    db.add(TenantSettings(tenant_id=tenant_id, key=key, value_json=json.dumps(value)))
    db.commit()


@pytest.fixture
def platform_groq(db_session):
    _global(db_session, "ai_provider", "groq")
    _global(db_session, "ai_model", "llama-3.1-8b-instant")
    _global(db_session, "groq_api_key", "PLATFORM-GROQ")
    _global(db_session, "anthropic_api_key", "PLATFORM-ANTHROPIC")


def test_no_overrides_uses_platform_config(db_session, test_tenant, platform_groq):
    assert resolve_ai_config(db_session, test_tenant.tenant_id) == (
        "groq", "llama-3.1-8b-instant", "PLATFORM-GROQ")


def test_provider_override_without_own_key_falls_back_to_platform(db_session, test_tenant, platform_groq):
    # The loophole: pick Anthropic and run on the platform's Anthropic key.
    _tenant(db_session, test_tenant.tenant_id, "ai_provider", "anthropic")
    _tenant(db_session, test_tenant.tenant_id, "ai_model", "claude-opus-5-5")
    provider, model, key = resolve_ai_config(db_session, test_tenant.tenant_id)
    assert (provider, model, key) == ("groq", "llama-3.1-8b-instant", "PLATFORM-GROQ")


def test_model_override_without_own_key_is_ignored(db_session, test_tenant, platform_groq):
    _tenant(db_session, test_tenant.tenant_id, "ai_model", "llama-3.3-70b-versatile")
    assert resolve_ai_config(db_session, test_tenant.tenant_id)[1] == "llama-3.1-8b-instant"


def test_bring_your_own_key_is_honoured(db_session, test_tenant, platform_groq):
    _tenant(db_session, test_tenant.tenant_id, "ai_provider", "anthropic")
    _tenant(db_session, test_tenant.tenant_id, "ai_model", "claude-opus-5-5")
    _tenant(db_session, test_tenant.tenant_id, "anthropic_api_key", "TENANT-ANTHROPIC")
    assert resolve_ai_config(db_session, test_tenant.tenant_id) == (
        "anthropic", "claude-opus-5-5", "TENANT-ANTHROPIC")


def test_own_key_for_platform_provider_keeps_platform_model(db_session, test_tenant, platform_groq):
    _tenant(db_session, test_tenant.tenant_id, "groq_api_key", "TENANT-GROQ")
    assert resolve_ai_config(db_session, test_tenant.tenant_id) == (
        "groq", "llama-3.1-8b-instant", "TENANT-GROQ")


def test_warmup_provider_override_needs_own_key(db_session, test_tenant, platform_groq):
    _global(db_session, "warmup_ai_provider", "groq")
    _tenant(db_session, test_tenant.tenant_id, "warmup_ai_provider", "anthropic")
    provider, _model, key = resolve_ai_config(
        db_session, test_tenant.tenant_id, provider_keys=("warmup_ai_provider",), model_key=None)
    assert (provider, key) == ("groq", "PLATFORM-GROQ")


def test_tenant_admin_can_still_save_own_ai_key(client, db_session, auth_headers, test_tenant):
    # Give admins full settings access, as production does, so this exercises the
    # platform-key guard rather than the tab-permission check.
    _global(db_session, "role_permissions", {"admin": {"settings": "full"}})
    r = client.put(f"{API}/settings/anthropic_api_key", headers=auth_headers,
                   json={"value": "sk-ant-tenant"})
    assert r.status_code == 200, r.text
