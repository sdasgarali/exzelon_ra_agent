"""Integration tests: notify a user when a deal is assigned to them, gated by
their per-user notification master toggles (in-app bell + email), plus the
self-service preferences endpoint."""
import pytest

from app.db.models.deal import Deal, DealStage
from app.db.models.notification import NotificationEntry

pytestmark = pytest.mark.integration


@pytest.fixture
def stage(db_session, test_tenant):
    s = DealStage(tenant_id=test_tenant.tenant_id, name="New Lead", stage_order=1, color="#111")
    db_session.add(s)
    db_session.commit()
    db_session.refresh(s)
    return s


def _mk_deal(db, tenant_id, stage_id, name="Acme — Jane"):
    d = Deal(tenant_id=tenant_id, name=name, stage_id=stage_id, value=1000, probability=20)
    db.add(d)
    db.commit()
    db.refresh(d)
    return d


def _notifs_for(db, user_id):
    return db.query(NotificationEntry).filter(
        NotificationEntry.user_id == user_id,
        NotificationEntry.category == "deal",
    ).all()


class TestAssignmentNotification:
    def test_assign_creates_inapp_notification_for_assignee(
        self, client, db_session, auth_headers, operator_user, test_tenant, stage, monkeypatch
    ):
        sent = []
        monkeypatch.setattr("app.services.email_verification._send_email",
                            lambda *a, **k: sent.append(a) or True)
        d = _mk_deal(db_session, test_tenant.tenant_id, stage.stage_id)
        resp = client.post(f"/api/v1/deals/{d.deal_id}/assign", headers=auth_headers,
                           json={"user_id": operator_user.user_id})
        assert resp.status_code == 200, resp.text

        notifs = _notifs_for(db_session, operator_user.user_id)
        assert len(notifs) == 1
        n = notifs[0]
        assert n.tenant_id == test_tenant.tenant_id
        assert "assigned" in n.title.lower()
        assert d.name in (n.message or "")
        assert n.link == f"/dashboard/deals?deal_id={d.deal_id}"
        # Email toggle defaults ON → one email fired to the assignee.
        assert len(sent) == 1

    def test_inapp_toggle_off_suppresses_notification(
        self, client, db_session, auth_headers, operator_user, test_tenant, stage, monkeypatch
    ):
        monkeypatch.setattr("app.services.email_verification._send_email", lambda *a, **k: True)
        operator_user.notify_inapp_enabled = False
        db_session.commit()
        d = _mk_deal(db_session, test_tenant.tenant_id, stage.stage_id)
        resp = client.post(f"/api/v1/deals/{d.deal_id}/assign", headers=auth_headers,
                           json={"user_id": operator_user.user_id})
        assert resp.status_code == 200
        assert _notifs_for(db_session, operator_user.user_id) == []

    def test_email_toggle_off_suppresses_email(
        self, client, db_session, auth_headers, operator_user, test_tenant, stage, monkeypatch
    ):
        sent = []
        monkeypatch.setattr("app.services.email_verification._send_email",
                            lambda *a, **k: sent.append(a) or True)
        operator_user.notify_email_enabled = False
        db_session.commit()
        d = _mk_deal(db_session, test_tenant.tenant_id, stage.stage_id)
        resp = client.post(f"/api/v1/deals/{d.deal_id}/assign", headers=auth_headers,
                           json={"user_id": operator_user.user_id})
        assert resp.status_code == 200
        # In-app still fires (default ON); email suppressed.
        assert len(_notifs_for(db_session, operator_user.user_id)) == 1
        assert sent == []

    def test_unassign_creates_no_notification(
        self, client, db_session, auth_headers, operator_user, test_tenant, stage, monkeypatch
    ):
        monkeypatch.setattr("app.services.email_verification._send_email", lambda *a, **k: True)
        d = _mk_deal(db_session, test_tenant.tenant_id, stage.stage_id, name="ToClear")
        d.owner_id = operator_user.user_id
        db_session.commit()
        resp = client.post(f"/api/v1/deals/{d.deal_id}/assign", headers=auth_headers,
                           json={"user_id": None})
        assert resp.status_code == 200
        assert _notifs_for(db_session, operator_user.user_id) == []


class TestNotificationPreferencesEndpoint:
    def test_get_me_exposes_defaults(self, client, operator_headers):
        me = client.get("/api/v1/auth/me", headers=operator_headers).json()
        assert me["notify_inapp_enabled"] is True
        assert me["notify_email_enabled"] is True

    def test_patch_updates_own_preferences(self, client, db_session, operator_headers, operator_user):
        resp = client.patch("/api/v1/auth/me/notification-preferences",
                            headers=operator_headers,
                            json={"notify_email_enabled": False})
        assert resp.status_code == 200, resp.text
        assert resp.json()["notify_email_enabled"] is False
        assert resp.json()["notify_inapp_enabled"] is True  # untouched
        db_session.refresh(operator_user)
        assert operator_user.notify_email_enabled is False

    def test_patch_partial_leaves_other_unchanged(self, client, operator_headers):
        resp = client.patch("/api/v1/auth/me/notification-preferences",
                            headers=operator_headers,
                            json={"notify_inapp_enabled": False})
        assert resp.status_code == 200
        body = resp.json()
        assert body["notify_inapp_enabled"] is False
        assert body["notify_email_enabled"] is True
