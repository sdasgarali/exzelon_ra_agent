"""Job Source APIs and Contacts settings tabs are super-admin only.

Both tabs hold the platform-wide provider keys (job boards, Resource Pool, contact
discovery) that every workspace falls back to. A workspace admin must not read,
change or test them, even when the role matrix grants the tab — reading them
returned the platform's keys in plain text.
"""
import json

import pytest

from app.api.deps.auth import SUPER_ADMIN_ONLY_SETTINGS_TABS
from app.db.models.settings import Settings

pytestmark = [pytest.mark.integration, pytest.mark.security]

PLATFORM_SECRET = "PLATFORM-SECRET"
# One key from each restricted tab, plus one from a tab admins may still use.
JOB_SOURCE_KEY = "adzuna_api_key"
CONTACTS_KEY = "apollo_api_key"
OPEN_TAB_KEY = "min_salary_threshold"


def _put_global(db, key, value):
    db.add(Settings(key=key, value_json=json.dumps(value), type="string"))
    db.commit()


@pytest.fixture
def platform_settings(db_session):
    """Platform keys in the global table and a role matrix that grants every tab."""
    _put_global(db_session, JOB_SOURCE_KEY, f"{PLATFORM_SECRET}-adzuna")
    _put_global(db_session, CONTACTS_KEY, f"{PLATFORM_SECRET}-apollo")
    _put_global(db_session, OPEN_TAB_KEY, 30000)
    _put_global(db_session, "role_permissions", {"admin": {"settings": "full"}})


def test_restricted_tabs_are_job_source_apis_and_contacts():
    assert SUPER_ADMIN_ONLY_SETTINGS_TABS == {"job_source_apis", "contacts"}


def test_admin_tab_permissions_deny_restricted_tabs(client, auth_headers, platform_settings):
    r = client.get("/api/v1/settings/my-permissions/settings-tabs", headers=auth_headers)
    assert r.status_code == 200
    perms = r.json()
    assert perms["job_source_apis"] == "no_access"
    assert perms["contacts"] == "no_access"
    # The matrix grant still applies to every other tab.
    assert perms["job_filters"] == "full"


def test_admin_settings_list_omits_restricted_keys(client, auth_headers, platform_settings):
    r = client.get("/api/v1/settings", headers=auth_headers)
    assert r.status_code == 200
    keys = {s["key"] for s in r.json()}
    assert JOB_SOURCE_KEY not in keys
    assert CONTACTS_KEY not in keys
    assert OPEN_TAB_KEY in keys
    assert PLATFORM_SECRET not in r.text


@pytest.mark.parametrize("key", [JOB_SOURCE_KEY, CONTACTS_KEY])
def test_admin_cannot_read_restricted_key(client, auth_headers, platform_settings, key):
    r = client.get(f"/api/v1/settings/{key}", headers=auth_headers)
    assert r.status_code == 403
    assert PLATFORM_SECRET not in r.text


@pytest.mark.parametrize("key", [JOB_SOURCE_KEY, CONTACTS_KEY])
def test_admin_cannot_write_restricted_key(client, auth_headers, platform_settings, key):
    r = client.put(f"/api/v1/settings/{key}", headers=auth_headers, json={"value": "tenant-key"})
    assert r.status_code == 403


@pytest.mark.parametrize("provider", ["adzuna", "apollo"])
def test_admin_cannot_test_restricted_provider(client, auth_headers, platform_settings, provider):
    r = client.post(f"/api/v1/settings/test-connection/{provider}", headers=auth_headers)
    assert r.status_code == 403


def test_super_admin_keeps_full_access(client, sa_headers, platform_settings):
    perms = client.get("/api/v1/settings/my-permissions/settings-tabs", headers=sa_headers).json()
    assert perms["job_source_apis"] == "full"
    assert perms["contacts"] == "full"
    r = client.get(f"/api/v1/settings/{CONTACTS_KEY}", headers=sa_headers)
    assert r.status_code == 200
    assert PLATFORM_SECRET in r.json()["value_json"]
