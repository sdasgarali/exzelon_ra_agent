"""Deliverability truthfulness + seed-test tenant scoping.

- GET /deliverability/health-summary computes from real mailbox columns,
  reports failed connections and never counts them as healthy.
- The mailbox API's computed `can_send` is false when the connection failed.
- /deliverability/seed-test/* is tenant scoped (404 for another tenant's
  mailbox or run) and the by-mailbox route no longer 500s.
"""
from datetime import datetime

import pytest

from app.core.security import create_access_token, get_password_hash
from app.db.models.seed_test import SeedTestAccount, SeedTestResult
from app.db.models.sender_mailbox import SenderMailbox, WarmupStatus
from app.db.models.tenant import Tenant, TenantPlan
from app.db.models.user import User, UserRole

pytestmark = pytest.mark.integration

API = "/api/v1/deliverability"


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
        tenant_id=tenant.tenant_id, email=email, password="fake-password",
        warmup_status=WarmupStatus.COLD_READY, is_active=True,
        connection_status="successful", daily_send_limit=30, emails_sent_today=0,
        total_emails_sent=100, bounce_count=1, reply_count=15, complaint_count=0,
        warmup_days_completed=30,
    )
    fields.update(kw)
    mb = SenderMailbox(**fields)
    db.add(mb)
    db.commit()
    db.refresh(mb)
    return mb


@pytest.fixture
def world(db_session, test_tenant):
    db = db_session
    tenant_b = Tenant(
        name="Other Org", slug="other-org", plan=TenantPlan.ENTERPRISE,
        max_users=999, max_mailboxes=999, max_contacts=999999,
        max_campaigns=999, max_leads=999999,
    )
    db.add(tenant_b)
    db.commit()
    db.refresh(tenant_b)
    return {
        "a": test_tenant, "b": tenant_b,
        "headers_a": _make_admin(db, test_tenant, "admin-a@tenant-a.com"),
        "headers_b": _make_admin(db, tenant_b, "admin-b@tenant-b.com"),
        "ok_a": _make_mailbox(db, test_tenant, "ok@tenant-a.com"),
        "failed_a": _make_mailbox(
            db, test_tenant, "failed@tenant-a.com", connection_status="failed",
            connection_error="535 auth failed",
        ),
        "mb_b": _make_mailbox(db, tenant_b, "x@tenant-b.com", connection_status="failed"),
    }


class TestHealthSummary:
    def test_counts_failed_connections_and_not_as_healthy(self, client, world):
        r = client.get(f"{API}/health-summary", headers=world["headers_a"])
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["total_mailboxes"] == 2          # tenant B's mailbox excluded
        assert body["failed_connection_count"] == 1
        assert body["healthy_count"] <= 1            # the failed one never counts
        assert body["avg_health_score"] < 100        # failed mailbox scores 0
        # No DNS check has run yet: reported as unchecked, not as "0 issues, all good".
        assert body["dns_unchecked_count"] == 2

    def test_all_failed_reports_zero_health(self, client, world):
        body = client.get(f"{API}/health-summary", headers=world["headers_b"]).json()
        assert body["total_mailboxes"] == 1
        assert body["failed_connection_count"] == 1
        assert body["healthy_count"] == 0
        assert body["avg_health_score"] == 0

    def test_dns_issues_from_real_dns_score(self, client, world, db_session):
        mb = world["ok_a"]
        mb.last_dns_check_at = datetime.utcnow()
        mb.dns_score = 40
        db_session.commit()
        body = client.get(f"{API}/health-summary", headers=world["headers_a"]).json()
        assert body["dns_issues_count"] == 1
        assert body["dns_unchecked_count"] == 1

    def test_mailbox_health_detail_failed_connection(self, client, world):
        h = world["headers_a"]
        r = client.get(f"{API}/mailbox/{world['failed_a'].mailbox_id}/health", headers=h)
        assert r.status_code == 200
        assert r.json()["health_score"] == 0
        assert r.json()["is_healthy"] is False
        assert client.get(f"{API}/mailbox/{world['mb_b'].mailbox_id}/health", headers=h).status_code == 404


class TestCanSend:
    def test_can_send_false_when_connection_failed(self, client, world):
        h = world["headers_a"]
        ok = client.get(f"/api/v1/mailboxes/{world['ok_a'].mailbox_id}", headers=h).json()
        failed = client.get(f"/api/v1/mailboxes/{world['failed_a'].mailbox_id}", headers=h).json()
        assert ok["can_send"] is True
        assert failed["can_send"] is False

    def test_list_and_stats_reflect_failed_connection(self, client, world):
        h = world["headers_a"]
        items = client.get("/api/v1/mailboxes", headers=h).json()["items"]
        by_email = {i["email"]: i["can_send"] for i in items}
        assert by_email == {"ok@tenant-a.com": True, "failed@tenant-a.com": False}
        stats = client.get("/api/v1/mailboxes/stats", headers=h).json()
        assert stats["total_daily_capacity"] == 30  # only the mailbox that can connect


class TestSeedTest:
    def test_seed_test_by_mailbox_scoped(self, client, world):
        h = world["headers_a"]
        # Before the fix this 500'd (tenant_filter called without the model).
        assert client.post(f"{API}/seed-test/{world['mb_b'].mailbox_id}", headers=h).status_code == 404
        r = client.post(f"{API}/seed-test/{world['ok_a'].mailbox_id}", headers=h)
        assert r.status_code == 200
        assert r.json() == {"error": "No seed test accounts configured"}

    def _make_run(self, db, mailbox, run_id):
        acct = db.query(SeedTestAccount).first()
        if acct is None:
            acct = SeedTestAccount(provider="gmail", email="seed@example.com", imap_password=None)
            db.add(acct)
            db.commit()
            db.refresh(acct)
        db.add(SeedTestResult(mailbox_id=mailbox.mailbox_id, test_run_id=run_id,
                              seed_account_id=acct.account_id))
        db.commit()

    def test_results_and_check_scoped(self, client, world, db_session, sa_headers):
        self._make_run(db_session, world["ok_a"], "run-a")
        self._make_run(db_session, world["mb_b"], "run-b")
        h = world["headers_a"]

        assert client.get(f"{API}/seed-test/run-b/results", headers=h).status_code == 404
        assert client.post(f"{API}/seed-test/run-b/check", headers=h).status_code == 404
        assert client.get(f"{API}/seed-test/nonexistent/results", headers=h).status_code == 404
        # B's pending result was not touched by A's attempted check.
        b_row = db_session.query(SeedTestResult).filter_by(test_run_id="run-b").one()
        assert b_row.checked_at is None

        r = client.get(f"{API}/seed-test/run-a/results", headers=h)
        assert r.status_code == 200 and len(r.json()) == 1
        r = client.post(f"{API}/seed-test/run-a/check", headers=h)
        assert r.status_code == 200
        assert r.json()["total"] == 1  # seed account has no IMAP password -> "error"

        # Super admin (no tenant) keeps the global view.
        assert client.get(f"{API}/seed-test/run-b/results", headers=sa_headers).status_code == 200
