"""The hourly peer-warmup / auto-reply jobs must process each tenant's mailboxes once.

Regression: the jobs looped over active tenants but did not restrict senders/repliers,
so every mailbox was processed once per active tenant per cycle.
"""
import pytest

from app.services.warmup import peer_warmup, scheduler

pytestmark = pytest.mark.unit


@pytest.fixture
def two_tenants(monkeypatch):
    monkeypatch.setattr(scheduler, "_is_warmup_job_enabled", lambda _j: True)
    monkeypatch.setattr(scheduler, "_get_active_tenant_ids", lambda: [1, 2])

    class _DB:
        def close(self):
            pass

    monkeypatch.setattr(scheduler, "_get_db", lambda: _DB())


def test_peer_cycle_scopes_senders_per_tenant(two_tenants, monkeypatch):
    calls = []
    monkeypatch.setattr(peer_warmup, "run_peer_warmup_cycle", lambda db, **kw: calls.append(kw) or {})
    scheduler.job_peer_warmup_cycle()
    assert calls == [{"tenant_id": 1, "sender_tenant_id": 1}, {"tenant_id": 2, "sender_tenant_id": 2}]


def test_auto_reply_scopes_repliers_per_tenant(two_tenants, monkeypatch):
    calls = []
    monkeypatch.setattr(peer_warmup, "run_auto_reply_cycle", lambda db, **kw: calls.append(kw) or {})
    scheduler.job_auto_reply_cycle()
    assert calls == [{"tenant_id": 1, "replier_tenant_id": 1}, {"tenant_id": 2, "replier_tenant_id": 2}]


def test_daily_assessment_runs_once_per_tenant(two_tenants, monkeypatch):
    """Regression: the nightly assessment ran once for all tenants and its JobRun was
    recorded under tenant 1, so other tenants' Assessment History stayed empty and
    their own warmup settings were ignored."""
    from app.services.pipelines import warmup_engine

    calls = []
    monkeypatch.setattr(warmup_engine, "run_warmup_assessment", lambda **kw: calls.append(kw) or {})
    scheduler.job_daily_assessment()
    assert calls == [{"triggered_by": "scheduler", "tenant_id": 1}, {"triggered_by": "scheduler", "tenant_id": 2}]


def test_daily_assessment_failure_does_not_stop_other_tenants(two_tenants, monkeypatch):
    from app.services.pipelines import warmup_engine

    seen = []

    def _run(**kw):
        seen.append(kw["tenant_id"])
        if kw["tenant_id"] == 1:
            raise RuntimeError("boom")
        return {}

    monkeypatch.setattr(warmup_engine, "run_warmup_assessment", _run)
    scheduler.job_daily_assessment()
    assert seen == [1, 2]
