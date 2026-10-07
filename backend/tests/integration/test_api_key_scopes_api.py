"""API-key scopes enforced end-to-end through the real auth dependency."""
import hashlib
from datetime import datetime, timedelta

import pytest

from app.db.models.api_key import ApiKey

pytestmark = pytest.mark.integration


def _create_key(client, auth_headers, scopes, **extra):
    r = client.post("/api/v1/integrations/api-keys", headers=auth_headers,
                    json={"name": f"mcp-{'-'.join(scopes)}", "scopes": scopes, **extra})
    assert r.status_code == 200, r.text
    return r.json()


def test_create_returns_key_once_and_lists_expiry(client, auth_headers):
    body = _create_key(client, auth_headers, ["read"], expires_in_days=30)
    assert body["key"].startswith("exz_")
    assert body["expires_at"] is not None
    # Regression: the prefix was 12 chars for an 8-char column, so every create 500'd on MySQL.
    assert len(body["key_prefix"]) <= ApiKey.__table__.c.key_prefix.type.length
    assert body["key"].startswith(body["key_prefix"])
    listed = client.get("/api/v1/integrations/api-keys", headers=auth_headers).json()
    row = next(k for k in listed if k["key_id"] == body["key_id"])
    assert "key" not in row and row["expires_at"] == body["expires_at"]


@pytest.mark.parametrize("scopes", [[], ["root"], ["read", "root"]])
def test_create_rejects_invalid_scopes(client, auth_headers, scopes):
    r = client.post("/api/v1/integrations/api-keys", headers=auth_headers,
                    json={"name": "bad", "scopes": scopes})
    assert r.status_code == 422


def test_create_rejects_out_of_range_expiry(client, auth_headers):
    r = client.post("/api/v1/integrations/api-keys", headers=auth_headers,
                    json={"name": "bad", "scopes": ["read"], "expires_in_days": 0})
    assert r.status_code == 422


def test_read_key_reads_but_cannot_write(client, auth_headers):
    key = _create_key(client, auth_headers, ["read"])["key"]
    h = {"X-API-Key": key}
    assert client.get("/api/v1/leads", headers=h).status_code == 200
    r = client.post("/api/v1/clients", headers=h, json={"client_name": "Acme"})
    assert r.status_code == 403
    assert "read-only" in r.json()["detail"]


def test_write_key_writes_but_cannot_delete(client, auth_headers):
    key = _create_key(client, auth_headers, ["write"])["key"]
    h = {"X-API-Key": key}
    r = client.post("/api/v1/clients", headers=h, json={"client_name": "Acme Scoped"})
    assert r.status_code in (200, 201), r.text
    client_id = r.json()["client_id"]
    r = client.delete(f"/api/v1/clients/{client_id}", headers=h)
    assert r.status_code == 403


def test_admin_key_can_delete(client, auth_headers):
    key = _create_key(client, auth_headers, ["admin"])["key"]
    h = {"X-API-Key": key}
    client_id = client.post("/api/v1/clients", headers=h,
                            json={"client_name": "Acme Admin"}).json()["client_id"]
    assert client.delete(f"/api/v1/clients/{client_id}", headers=h).status_code in (200, 204)


def test_no_key_can_mint_or_revoke_keys(client, auth_headers):
    created = _create_key(client, auth_headers, ["admin"])
    h = {"X-API-Key": created["key"]}
    r = client.post("/api/v1/integrations/api-keys", headers=h,
                    json={"name": "escalate", "scopes": ["admin"]})
    assert r.status_code == 403
    assert client.delete(f"/api/v1/integrations/api-keys/{created['key_id']}", headers=h).status_code == 403


def test_expired_key_rejected(client, db_session, auth_headers):
    created = _create_key(client, auth_headers, ["read"])
    row = db_session.query(ApiKey).filter(
        ApiKey.key_hash == hashlib.sha256(created["key"].encode()).hexdigest()).one()
    row.expires_at = datetime.utcnow() - timedelta(minutes=1)
    db_session.commit()
    assert client.get("/api/v1/leads", headers={"X-API-Key": created["key"]}).status_code == 401


def test_revoked_key_rejected(client, auth_headers):
    created = _create_key(client, auth_headers, ["read"])
    client.delete(f"/api/v1/integrations/api-keys/{created['key_id']}", headers=auth_headers)
    assert client.get("/api/v1/leads", headers={"X-API-Key": created["key"]}).status_code == 401
