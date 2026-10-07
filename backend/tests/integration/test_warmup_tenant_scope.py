"""Tenant isolation for /warmup routes that take a mailbox / alert / log id.

Tenant A's admin must get 404 for tenant B's mailbox, alert, log or warmup
email, and must not see or change B's rows through list / bulk routes. A super
admin without an impersonated tenant keeps the all-tenant view.

Also covers: POST /warmup/assess scope + JobRun attribution, and the
`recovering` warmup status serializing on mailbox responses.
"""
import json
from datetime import date, datetime

import pytest

from app.core.security import create_access_token, get_password_hash
from app.db.models.job_run import JobRun
from app.db.models.sender_mailbox import SenderMailbox, WarmupStatus
from app.db.models.settings import Settings
from app.db.models.tenant import Tenant, TenantPlan
from app.db.models.user import User, UserRole
from app.db.models.warmup_alert import AlertSeverity, AlertType, WarmupAlert
from app.db.models.warmup_daily_log import WarmupDailyLog
from app.db.models.warmup_email import WarmupEmail
from app.db.models.warmup_profile import WarmupProfile

pytestmark = pytest.mark.integration

API = "/api/v1/warmup"


# ---------------------------------------------------------------------------
# Fixtures: two tenants, an admin each, one mailbox each with alert/log/email
# ---------------------------------------------------------------------------

def _make_admin(db, tenant, email):
    user = User(
        email=email, password_hash=get_password_hash("testpassword"),
        full_name=f"Admin {email}", role=UserRole.ADMIN,
        is_active=True, is_verified=True, tenant_id=tenant.tenant_id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_access_token(data={
        "sub": user.email, "role": user.role,
        "tenant_id": user.tenant_id, "plan": "enterprise",
    })
    return {"Authorization": f"Bearer {token}"}


def _make_mailbox(db, tenant, email, **kw):
    fields = dict(
        tenant_id=tenant.tenant_id, email=email, display_name=email.split("@")[0],
        password="fake-password", warmup_status=WarmupStatus.WARMING_UP,
        is_active=True, connection_status="successful", daily_send_limit=30,
        emails_sent_today=0, total_emails_sent=100, bounce_count=1,
        reply_count=10, complaint_count=0, warmup_days_completed=3,
    )
    fields.update(kw)
    mb = SenderMailbox(**fields)
    db.add(mb)
    db.commit()
    db.refresh(mb)
    return mb


@pytest.fixture
def world(db_session, test_tenant):
    """Tenant A (test_tenant) and tenant B, each with an admin, mailbox, alert,
    daily log and peer warmup email. Admins get warmup 'full' via the global
    role_permissions matrix (not seeded in the test DB by default)."""
    db = db_session
    db.add(Settings(
        key="role_permissions", type="json",
        value_json=json.dumps({"admin": {"warmup": "full"}}),
    ))
    db.commit()

    tenant_b = Tenant(
        name="Other Org", slug="other-org", plan=TenantPlan.ENTERPRISE,
        max_users=999, max_mailboxes=999, max_contacts=999999,
        max_campaigns=999, max_leads=999999,
    )
    db.add(tenant_b)
    db.commit()
    db.refresh(tenant_b)

    headers_a = _make_admin(db, test_tenant, "admin-a@tenant-a.com")
    headers_b = _make_admin(db, tenant_b, "admin-b@tenant-b.com")

    mb_a = _make_mailbox(db, test_tenant, "sender@tenant-a.com")
    mb_b = _make_mailbox(db, tenant_b, "sender@tenant-b.com")

    alerts = {}
    logs = {}
    emails = {}
    for key, mb in (("a", mb_a), ("b", mb_b)):
        alert = WarmupAlert(
            mailbox_id=mb.mailbox_id, alert_type=AlertType.HEALTH_DROP,
            severity=AlertSeverity.WARNING, title=f"Alert {key}", is_read=False,
        )
        log = WarmupDailyLog(
            mailbox_id=mb.mailbox_id, log_date=date.today(), emails_sent=5,
            health_score=80.0,
        )
        db.add_all([alert, log])
        db.commit()
        db.refresh(alert)
        db.refresh(log)
        alerts[key] = alert
        logs[key] = log

    # B-only warmup email (B sends to B) and a cross-tenant one (A -> B).
    mb_b2 = _make_mailbox(db, tenant_b, "second@tenant-b.com")
    e_b = WarmupEmail(sender_mailbox_id=mb_b.mailbox_id, receiver_mailbox_id=mb_b2.mailbox_id,
                      subject="B internal", body_text="secret b", sent_at=datetime.utcnow())
    e_ab = WarmupEmail(sender_mailbox_id=mb_a.mailbox_id, receiver_mailbox_id=mb_b.mailbox_id,
                       subject="A to B", body_text="hello", sent_at=datetime.utcnow())
    db.add_all([e_b, e_ab])
    db.commit()
    db.refresh(e_b)
    db.refresh(e_ab)
    emails["b"] = e_b
    emails["ab"] = e_ab

    profile = WarmupProfile(name="Scope Profile", config_json="{}", is_system=False, is_default=False)
    db.add(profile)
    db.commit()
    db.refresh(profile)

    return {
        "a": test_tenant, "b": tenant_b,
        "headers_a": headers_a, "headers_b": headers_b,
        "mb_a": mb_a, "mb_b": mb_b, "mb_b2": mb_b2,
        "alerts": alerts, "logs": logs, "emails": emails, "profile": profile,
    }


# ---------------------------------------------------------------------------
# By-id routes: other tenant's id -> 404, own id -> OK
# ---------------------------------------------------------------------------

class TestMailboxByIdRoutes:
    def test_assess_single(self, client, world):
        h = world["headers_a"]
        assert client.post(f"{API}/assess/{world['mb_b'].mailbox_id}", headers=h).status_code == 404
        r = client.post(f"{API}/assess/{world['mb_a'].mailbox_id}", headers=h)
        assert r.status_code == 200, r.text
        assert r.json()["assessed"] == 1

    def test_dns_results(self, client, world):
        h = world["headers_a"]
        assert client.get(f"{API}/dns/{world['mb_b'].mailbox_id}", headers=h).status_code == 404
        assert client.get(f"{API}/dns/{world['mb_a'].mailbox_id}", headers=h).status_code == 200

    def test_blacklist_results(self, client, world):
        h = world["headers_a"]
        assert client.get(f"{API}/blacklist/{world['mb_b'].mailbox_id}", headers=h).status_code == 404
        assert client.get(f"{API}/blacklist/{world['mb_a'].mailbox_id}", headers=h).status_code == 200

    def test_dns_and_blacklist_check_single(self, client, world, monkeypatch):
        import app.api.endpoints.warmup as ep
        monkeypatch.setattr(ep, "run_dns_health_check", lambda mid, db, tenant_id=None: {"ok": mid})
        monkeypatch.setattr(ep, "run_bl_check", lambda mid, db, tenant_id=None: {"ok": mid})
        h = world["headers_a"]
        b, a = world["mb_b"].mailbox_id, world["mb_a"].mailbox_id
        assert client.post(f"{API}/dns-check?mailbox_id={b}", headers=h).status_code == 404
        assert client.post(f"{API}/blacklist-check?mailbox_id={b}", headers=h).status_code == 404
        assert client.post(f"{API}/dns-check?mailbox_id={a}", headers=h).status_code == 200
        assert client.post(f"{API}/blacklist-check?mailbox_id={a}", headers=h).status_code == 200

    def test_placement_test(self, client, world, monkeypatch):
        import app.api.endpoints.warmup as ep
        calls = []
        monkeypatch.setattr(ep, "run_placement_test",
                            lambda mid, db, tenant_id=None: calls.append(mid) or {"ok": True})
        h = world["headers_a"]
        assert client.post(f"{API}/placement-test/{world['mb_b'].mailbox_id}", headers=h).status_code == 404
        assert calls == []
        assert client.post(f"{API}/placement-test/{world['mb_a'].mailbox_id}", headers=h).status_code == 200
        assert calls == [world["mb_a"].mailbox_id]

    def test_apply_profile(self, client, world, db_session):
        h = world["headers_a"]
        p = world["profile"].id
        assert client.post(f"{API}/profiles/{p}/apply/{world['mb_b'].mailbox_id}", headers=h).status_code == 404
        db_session.refresh(world["mb_b"])
        assert world["mb_b"].warmup_profile_id is None
        assert client.post(f"{API}/profiles/{p}/apply/{world['mb_a'].mailbox_id}", headers=h).status_code == 200

    def test_start_recovery(self, client, world, db_session):
        h = world["headers_a"]
        assert client.post(f"{API}/recovery/{world['mb_b'].mailbox_id}/start", headers=h).status_code == 404
        db_session.refresh(world["mb_b"])
        assert world["mb_b"].warmup_status == WarmupStatus.WARMING_UP
        assert client.post(f"{API}/recovery/{world['mb_a'].mailbox_id}/start", headers=h).status_code == 200

    def test_peer_send_other_tenant_mailbox(self, client, world, monkeypatch):
        import app.api.endpoints.warmup as ep
        seen = {}

        def fake_cycle(db, mailbox_id=None, tenant_id=None, sender_tenant_id=None):
            seen.update(mailbox_id=mailbox_id, sender_tenant_id=sender_tenant_id)
            return {"sent": 0}

        monkeypatch.setattr(ep, "run_peer_warmup_cycle", fake_cycle)
        h = world["headers_a"]
        assert client.post(f"{API}/peer/send?mailbox_id={world['mb_b'].mailbox_id}", headers=h).status_code == 404
        assert seen == {}
        assert client.post(f"{API}/peer/send", headers=h).status_code == 200
        assert seen["sender_tenant_id"] == world["a"].tenant_id


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------

class TestAlerts:
    def test_list_only_own(self, client, world):
        r = client.get(f"{API}/alerts", headers=world["headers_a"])
        assert r.status_code == 200
        body = r.json()
        assert [a["id"] for a in body["items"]] == [world["alerts"]["a"].id]
        assert body["total"] == 1
        assert body["unread_count"] == 1

    def test_unread_count_only_own(self, client, world):
        r = client.get(f"{API}/alerts/unread-count", headers=world["headers_a"])
        assert r.json() == {"unread_count": 1}

    def test_mark_read_other_tenant_404(self, client, world, db_session):
        h = world["headers_a"]
        assert client.put(f"{API}/alerts/{world['alerts']['b'].id}/read", headers=h).status_code == 404
        db_session.refresh(world["alerts"]["b"])
        assert world["alerts"]["b"].is_read is False
        assert client.put(f"{API}/alerts/{world['alerts']['a'].id}/read", headers=h).status_code == 200

    def test_read_all_only_own(self, client, world, db_session):
        r = client.put(f"{API}/alerts/read-all", headers=world["headers_a"])
        assert r.status_code == 200
        assert r.json()["updated"] == 1
        db_session.refresh(world["alerts"]["a"])
        db_session.refresh(world["alerts"]["b"])
        assert world["alerts"]["a"].is_read is True
        assert world["alerts"]["b"].is_read is False

    def test_super_admin_sees_all(self, client, world, sa_headers):
        r = client.get(f"{API}/alerts", headers=sa_headers)
        assert r.json()["total"] == 2


# ---------------------------------------------------------------------------
# Analytics, peer history, export
# ---------------------------------------------------------------------------

class TestLogsAndHistory:
    def test_analytics_by_mailbox(self, client, world):
        h = world["headers_a"]
        assert client.get(f"{API}/analytics?mailbox_id={world['mb_b'].mailbox_id}", headers=h).status_code == 404
        r = client.get(f"{API}/analytics?mailbox_id={world['mb_a'].mailbox_id}", headers=h)
        assert r.status_code == 200
        assert r.json()["summary"]["log_count"] == 1

    def test_analytics_all_only_own(self, client, world, sa_headers):
        r = client.get(f"{API}/analytics", headers=world["headers_a"])
        assert r.status_code == 200
        assert [log["mailbox_id"] for log in r.json()["daily_logs"]] == [world["mb_a"].mailbox_id]
        # super admin, no tenant: all tenants
        assert client.get(f"{API}/analytics", headers=sa_headers).json()["summary"]["log_count"] == 2

    def test_peer_history_list(self, client, world):
        h = world["headers_a"]
        assert client.get(f"{API}/peer/history?mailbox_id={world['mb_b'].mailbox_id}", headers=h).status_code == 404
        r = client.get(f"{API}/peer/history", headers=h)
        assert r.status_code == 200
        ids = {e["id"] for e in r.json()["items"]}
        assert ids == {world["emails"]["ab"].id}  # B's internal email hidden

    def test_peer_history_detail(self, client, world):
        h = world["headers_a"]
        assert client.get(f"{API}/peer/history/{world['emails']['b'].id}", headers=h).status_code == 404
        r = client.get(f"{API}/peer/history/{world['emails']['ab'].id}", headers=h)
        assert r.status_code == 200
        body = r.json()
        assert body["sender_email"] == "sender@tenant-a.com"
        assert body["receiver_email"] is None  # other tenant's address not revealed

    def test_export_only_own(self, client, world):
        h = world["headers_a"]
        assert client.get(f"{API}/export?format=json&mailbox_ids={world['mb_b'].mailbox_id}",
                          headers=h).status_code == 404
        r = client.get(f"{API}/export?format=json", headers=h)
        assert r.status_code == 200
        report = json.loads(r.content)["report"]
        assert {row["mailbox_id"] for row in report} == {world["mb_a"].mailbox_id}


# ---------------------------------------------------------------------------
# POST /warmup/assess scope
# ---------------------------------------------------------------------------

class TestAssessAll:
    def test_tenant_admin_assesses_only_own_tenant(self, client, world, db_session):
        r = client.post(f"{API}/assess", headers=world["headers_a"])
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["assessed"] == 1
        assert {d["mailbox_id"] for d in body["details"]} == {world["mb_a"].mailbox_id}
        job = db_session.query(JobRun).filter(JobRun.run_id == body["run_id"]).one()
        assert job.tenant_id == world["a"].tenant_id

    def test_impersonating_super_admin_scoped(self, client, world, sa_headers, db_session):
        h = {**sa_headers, "X-Tenant-ID": str(world["b"].tenant_id)}
        body = client.post(f"{API}/assess", headers=h).json()
        assert {d["mailbox_id"] for d in body["details"]} == {
            world["mb_b"].mailbox_id, world["mb_b2"].mailbox_id,
        }
        job = db_session.query(JobRun).filter(JobRun.run_id == body["run_id"]).one()
        assert job.tenant_id == world["b"].tenant_id

    def test_super_admin_without_tenant_assesses_all(self, client, world, sa_headers):
        body = client.post(f"{API}/assess", headers=sa_headers).json()
        assert body["assessed"] == 3

    def test_engine_default_still_assesses_every_tenant(self, world, db_session):
        """The nightly scheduler calls run_warmup_assessment(triggered_by='scheduler')
        with no tenant: it must still cover all tenants."""
        from app.services.pipelines.warmup_engine import run_warmup_assessment
        result = run_warmup_assessment(triggered_by="scheduler", db=db_session)
        assert result["assessed"] == 3

    def test_scheduler_job_calls_engine_unscoped(self, monkeypatch):
        import app.services.pipelines.warmup_engine as engine
        import app.services.warmup.scheduler as sched
        calls = []
        monkeypatch.setattr(sched, "_is_warmup_job_enabled", lambda job_id: True)
        monkeypatch.setattr(engine, "run_warmup_assessment",
                            lambda **kw: calls.append(kw) or {"assessed": 0})
        sched.job_daily_assessment()
        assert calls and "tenant_id" not in calls[0]


# ---------------------------------------------------------------------------
# `recovering` status
# ---------------------------------------------------------------------------

class TestRecoveringStatus:
    def test_recovering_mailbox_serializes(self, client, world):
        h = world["headers_a"]
        mid = world["mb_a"].mailbox_id
        assert client.post(f"{API}/recovery/{mid}/start", headers=h).status_code == 200
        r = client.get(f"/api/v1/mailboxes/{mid}", headers=h)
        assert r.status_code == 200, r.text
        assert r.json()["warmup_status"] == "recovering"
        r = client.get("/api/v1/mailboxes", headers=h)
        assert r.status_code == 200, r.text
        r = client.get(f"{API}/status", headers=h)
        assert r.status_code == 200
        assert r.json()["recovering_count"] == 1

    def test_clients_cannot_set_recovering_directly(self, client, world):
        h = world["headers_a"]
        mid = world["mb_a"].mailbox_id
        r = client.post(f"/api/v1/mailboxes/{mid}/update-status?new_status=recovering", headers=h)
        assert r.status_code == 400
        r = client.put(f"/api/v1/mailboxes/{mid}", json={"warmup_status": "recovering"}, headers=h)
        assert r.status_code == 422
        # A normal transition still works.
        r = client.post(f"/api/v1/mailboxes/{mid}/update-status?new_status=paused", headers=h)
        assert r.status_code == 200
        assert r.json()["mailbox"]["warmup_status"] == "paused"
