"""Deleting a user who has history (2026-09-23 prod bug).

`DELETE /users/{id}` returned 500 in production — MySQL 1451, because `login_history`
(and 18 other NO ACTION foreign keys) still pointed at the user. SQLite ignores FKs
unless told otherwise, which is why no test caught it; these tests switch them on.
"""
import pytest
from sqlalchemy import text

from app.core.security import get_password_hash
from app.db.models.api_key import ApiKey
from app.db.models.icp_profile import ICPProfile
from app.db.models.login_history import LoginHistory
from app.db.models.saved_search import SavedSearch
from app.db.models.user import User

pytestmark = pytest.mark.integration


@pytest.fixture
def enforce_fks(db_session):
    db_session.execute(text("PRAGMA foreign_keys=ON"))
    yield
    db_session.execute(text("PRAGMA foreign_keys=OFF"))


@pytest.fixture
def user_with_history(db_session, test_tenant):
    u = User(email="leaver@test.com", password_hash=get_password_hash("x"), full_name="Leaver",
             role="recruiter", is_active=True, is_verified=True, tenant_id=test_tenant.tenant_id)
    db_session.add(u)
    db_session.flush()
    db_session.add_all([
        LoginHistory(user_id=u.user_id, email_attempted=u.email, success=True),
        ApiKey(tenant_id=test_tenant.tenant_id, name="k", key_hash="h" * 64, key_prefix="abcd1234",
               user_id=u.user_id),
        SavedSearch(tenant_id=test_tenant.tenant_id, name="s", filters_json="{}", user_id=u.user_id),
        ICPProfile(tenant_id=test_tenant.tenant_id, name="ICP", user_id=u.user_id),
    ])
    db_session.commit()
    return u


def test_user_with_history_can_be_deleted(client, db_session, sa_headers, user_with_history,
                                          super_admin_user, enforce_fks):
    uid = user_with_history.user_id
    resp = client.delete(f"/api/v1/users/{uid}", headers=sa_headers)
    assert resp.status_code == 204, resp.text
    db_session.expire_all()

    assert db_session.query(User).filter_by(user_id=uid).first() is None
    # History survives, detached from the deleted user.
    history = db_session.query(LoginHistory).filter_by(email_attempted="leaver@test.com").one()
    assert history.user_id is None
    # Personal rows go with them — no orphaned live API key.
    assert db_session.query(ApiKey).filter_by(user_id=uid).count() == 0
    assert db_session.query(SavedSearch).filter_by(user_id=uid).count() == 0
    # Shared workspace data is kept and handed to the admin who deleted the user.
    icp = db_session.query(ICPProfile).filter_by(name="ICP").one()
    assert icp.user_id == super_admin_user.user_id


def test_references_are_read_from_the_schema_not_a_hardcoded_list(db_session):
    from app.services.user_deletion import _references_to_users
    refs = {(t, c) for t, c, _ in _references_to_users(db_session)}
    for expected in [("login_history", "user_id"), ("api_keys", "user_id"),
                     ("deals", "owner_id"), ("icp_profiles", "user_id")]:
        assert expected in refs
