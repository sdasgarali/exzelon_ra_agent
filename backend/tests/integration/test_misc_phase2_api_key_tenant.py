"""Workspace selection with API keys (MCP phase 2).

The MCP connector sends ``X-Tenant-ID`` for super-admin keys. It must be honoured for a
super admin authenticated by ``X-API-Key`` and ignored for everyone else.
"""
import hashlib
import json
import secrets

import pytest

from app.db.models.api_key import ApiKey
from app.db.models.client import ClientInfo
from app.db.models.tenant import Tenant, TenantPlan

pytestmark = pytest.mark.integration


def _make_key(db, user, tenant_id, scopes=("read",)):
    raw = "exz_" + secrets.token_hex(16)
    db.add(ApiKey(tenant_id=tenant_id, name="mcp", key_hash=hashlib.sha256(raw.encode()).hexdigest(),
                  key_prefix=raw[:8], scopes_json=json.dumps(list(scopes)), user_id=user.user_id,
                  is_active=True))
    db.commit()
    return {"X-API-Key": raw}


@pytest.fixture
def tenant_b(db_session):
    t = Tenant(name="Bravo Co", slug="bravo-co", plan=TenantPlan.STARTER, max_users=5, max_mailboxes=5,
               max_contacts=500, max_campaigns=5, max_leads=500)
    db_session.add(t)
    db_session.commit()
    db_session.refresh(t)
    return t


@pytest.fixture
def clients_ab(db_session, test_tenant, tenant_b):
    db_session.add_all([
        ClientInfo(tenant_id=test_tenant.tenant_id, client_name="Alpha Only Client"),
        ClientInfo(tenant_id=tenant_b.tenant_id, client_name="Bravo Only Client"),
    ])
    db_session.commit()


def _client_names(resp):
    assert resp.status_code == 200, resp.text
    body = resp.json()
    items = body["items"] if isinstance(body, dict) else body
    return {c["client_name"] for c in items}


def test_super_admin_key_honours_x_tenant_id(client, db_session, super_admin_user,
                                             test_tenant, tenant_b, clients_ab):
    h = _make_key(db_session, super_admin_user, test_tenant.tenant_id)
    names_b = _client_names(client.get("/api/v1/clients", headers={**h, "X-Tenant-ID": str(tenant_b.tenant_id)}))
    assert names_b == {"Bravo Only Client"}
    names_a = _client_names(client.get("/api/v1/clients", headers={**h, "X-Tenant-ID": str(test_tenant.tenant_id)}))
    assert names_a == {"Alpha Only Client"}


def test_super_admin_key_without_header_is_global(client, db_session, super_admin_user,
                                                  test_tenant, tenant_b, clients_ab):
    h = _make_key(db_session, super_admin_user, test_tenant.tenant_id)
    names = _client_names(client.get("/api/v1/clients", headers=h))
    assert {"Alpha Only Client", "Bravo Only Client"} <= names


def test_tenant_admin_key_ignores_x_tenant_id(client, db_session, admin_user,
                                              test_tenant, tenant_b, clients_ab):
    h = _make_key(db_session, admin_user, test_tenant.tenant_id)
    names = _client_names(client.get("/api/v1/clients", headers={**h, "X-Tenant-ID": str(tenant_b.tenant_id)}))
    assert names == {"Alpha Only Client"}


def test_tenant_admin_key_cannot_write_into_other_tenant(client, db_session, admin_user,
                                                         test_tenant, tenant_b):
    h = _make_key(db_session, admin_user, test_tenant.tenant_id, scopes=("write",))
    r = client.post("/api/v1/clients", headers={**h, "X-Tenant-ID": str(tenant_b.tenant_id)},
                    json={"client_name": "Smuggled Client"})
    assert r.status_code in (200, 201), r.text
    row = db_session.query(ClientInfo).filter(ClientInfo.client_name == "Smuggled Client").one()
    assert row.tenant_id == test_tenant.tenant_id


def test_tenant_jwt_ignores_x_tenant_id(client, auth_headers, tenant_b, clients_ab):
    names = _client_names(client.get("/api/v1/clients",
                                     headers={**auth_headers, "X-Tenant-ID": str(tenant_b.tenant_id)}))
    assert names == {"Alpha Only Client"}


# ── compute-only POSTs reachable with a read key (scope check passes; handler runs) ──

@pytest.mark.parametrize("path", [
    "/api/v1/campaigns/999999/ai-suggest-subjects",
    "/api/v1/inbox/threads/no-such-thread/suggest-reply",
    "/api/v1/templates/999999/preview",
])
def test_read_key_reaches_compute_only_posts(client, db_session, admin_user, test_tenant, path):
    h = _make_key(db_session, admin_user, test_tenant.tenant_id, scopes=("read",))
    r = client.post(path, headers=h)
    assert r.status_code == 404, r.text  # not 403: the scope allowed it, the id just doesn't exist


def test_read_key_still_blocked_on_template_duplicate(client, db_session, admin_user, test_tenant):
    h = _make_key(db_session, admin_user, test_tenant.tenant_id, scopes=("read",))
    assert client.post("/api/v1/templates/1/duplicate", headers=h).status_code == 403


# ── /admin/tenants for list_workspaces ─────────────────────────────────────────

def test_admin_tenants_list_with_super_admin_read_key(client, db_session, super_admin_user,
                                                       test_tenant, tenant_b):
    h = _make_key(db_session, super_admin_user, test_tenant.tenant_id, scopes=("read",))
    r = client.get("/api/v1/admin/tenants", headers=h)
    assert r.status_code == 200, r.text
    rows = {t["tenant_id"]: t for t in r.json()}
    assert {test_tenant.tenant_id, tenant_b.tenant_id} <= set(rows)
    b = rows[tenant_b.tenant_id]
    assert b["name"] == "Bravo Co"
    assert isinstance(b["plan"], str) and b["plan"]
    assert b["is_active"] is True
    for field in ("slug", "user_count", "lead_count", "contact_count", "mailbox_count", "campaign_count"):
        assert field in b


def test_admin_tenants_list_denied_for_tenant_admin_key(client, db_session, admin_user, test_tenant):
    h = _make_key(db_session, admin_user, test_tenant.tenant_id, scopes=("admin",))
    assert client.get("/api/v1/admin/tenants", headers=h).status_code == 403


def test_super_admin_read_key_cannot_create_tenant(client, db_session, super_admin_user, test_tenant):
    h = _make_key(db_session, super_admin_user, test_tenant.tenant_id, scopes=("read",))
    assert client.post("/api/v1/admin/tenants", headers=h, json={"name": "Nope"}).status_code == 403
