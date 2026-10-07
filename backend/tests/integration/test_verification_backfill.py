"""The startup verification backfill must never verify a self-signup.

It used to run `UPDATE users SET is_verified = 1` for every unverified row on every
start, so any signup — with an address the person did not own — became verified at
the next restart or deploy.
"""
from datetime import datetime

import pytest

from app.core.security import get_password_hash
from app.db.models.user import User, UserRole
from app.main import backfill_legacy_verified_users

pytestmark = pytest.mark.integration


def _user(db, email, tenant_id, sent_at):
    u = User(
        email=email, password_hash=get_password_hash("SecurePass123!"),
        full_name="X", role=UserRole.ADMIN, is_active=True, tenant_id=tenant_id,
        is_verified=False, verification_sent_at=sent_at,
    )
    db.add(u)
    db.commit()
    return u


def test_backfill_skips_pending_self_signup_but_verifies_legacy_rows(db_session, test_tenant):
    signup = _user(db_session, "signup@example.com", test_tenant.tenant_id, datetime.utcnow())
    legacy = _user(db_session, "legacy@example.com", test_tenant.tenant_id, None)

    backfill_legacy_verified_users(db_session.connection())
    db_session.commit()
    db_session.expire_all()

    assert db_session.get(User, signup.user_id).is_verified is False
    assert db_session.get(User, legacy.user_id).is_verified is True


def test_admin_created_user_is_verified_and_can_log_in(client, db_session, sa_headers, test_tenant):
    resp = client.post("/api/v1/users", json={
        "email": "made-by-admin@example.com",
        "password": "SecurePass123!",
        "full_name": "Made By Admin",
        "role": "recruiter",
        "tenant_id": test_tenant.tenant_id,
    }, headers=sa_headers)
    assert resp.status_code == 201

    user = db_session.query(User).filter(User.email == "made-by-admin@example.com").one()
    assert user.is_verified is True

    login = client.post("/api/v1/auth/login", data={
        "username": "made-by-admin@example.com", "password": "SecurePass123!",
    })
    assert login.status_code == 200, login.text
