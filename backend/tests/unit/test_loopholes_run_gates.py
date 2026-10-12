"""Run-sized credit gates added at integration: outreach runs, forced AI summary
regeneration, and scheduled intent scans (Plan_Credit_Loopholes.md, integration)."""
from contextlib import contextmanager

import pytest

from app.core.credit_costs import estimate_run_credits
from app.services.credit_metering import get_balance

pytestmark = pytest.mark.unit

API = "/api/v1"


def _enforce(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "CREDIT_ENFORCEMENT_ENABLED", True)


def _set_available(db, tenant_id, credits):
    balance = get_balance(db, tenant_id)
    balance.allowance_credits = float(credits)
    balance.topup_credits = 0.0
    db.commit()


def test_estimates_for_outreach_and_intent():
    assert estimate_run_credits("outreach", units=7) == 7
    assert estimate_run_credits("outreach") == 25
    assert estimate_run_credits("intent_scan") == 10


# --- outreach run --------------------------------------------------------------

@pytest.fixture
def outreach_access(monkeypatch):
    """Grant the admin the outreach tab, as production roles do, so these tests hit
    the credit gate rather than the tab-permission check."""
    monkeypatch.setattr("app.api.deps.auth.get_module_tab_access",
                        lambda *a, **k: "read_write")


def test_outreach_run_needs_more_than_one_credit(client, db_session, test_tenant, auth_headers, monkeypatch, outreach_access):
    _enforce(monkeypatch)
    _set_available(db_session, test_tenant.tenant_id, 1)
    r = client.post(f"{API}/pipelines/outreach/run?mode=mailmerge&dry_run=true",
                    headers=auth_headers, json={"lead_ids": [1, 2, 3, 4, 5]})
    assert r.status_code == 402, r.text


def test_outreach_run_allowed_when_budget_covers_selection(client, db_session, test_tenant, auth_headers, monkeypatch, outreach_access):
    _enforce(monkeypatch)
    _set_available(db_session, test_tenant.tenant_id, 100)
    monkeypatch.setattr("app.services.pipelines.outreach.run_outreach_mailmerge_pipeline",
                        lambda **k: None)
    r = client.post(f"{API}/pipelines/outreach/run?mode=mailmerge&dry_run=true",
                    headers=auth_headers, json={"lead_ids": [1, 2, 3]})
    assert r.status_code != 402, r.text


# --- forced summary regeneration ----------------------------------------------

def _finished_run(db, tenant_id):
    from app.db.models.job_run import JobRun, JobStatus
    run = JobRun(tenant_id=tenant_id, pipeline_name="lead_sourcing",
                 status=JobStatus.COMPLETED, triggered_by="t@test.com",
                 summary_json='{"source_breakdown": {}}')
    db.add(run)
    db.commit()
    return run


def test_summary_regenerate_blocked_without_credits(client, db_session, test_tenant, auth_headers, monkeypatch):
    _enforce(monkeypatch)
    _set_available(db_session, test_tenant.tenant_id, 0)
    run = _finished_run(db_session, test_tenant.tenant_id)
    r = client.get(f"{API}/pipelines/runs/{run.run_id}/summary?regenerate=true", headers=auth_headers)
    assert r.status_code == 402, r.text


def test_cached_summary_free_without_credits(client, db_session, test_tenant, auth_headers, monkeypatch):
    _enforce(monkeypatch)
    _set_available(db_session, test_tenant.tenant_id, 0)
    run = _finished_run(db_session, test_tenant.tenant_id)
    r = client.get(f"{API}/pipelines/runs/{run.run_id}/summary", headers=auth_headers)
    assert r.status_code == 200, r.text


# --- scheduled intent scans ----------------------------------------------------

@contextmanager
def _lock(_name):
    yield True


def _intent_scheduler(monkeypatch, tenant_id, calls):
    from app.services.warmup import scheduler
    from tests.conftest import TestingSessionLocal
    monkeypatch.setattr(scheduler, "_get_db", lambda: TestingSessionLocal())
    monkeypatch.setattr(scheduler, "_get_active_tenant_ids", lambda: [tenant_id])
    monkeypatch.setattr(scheduler, "_is_job_enabled", lambda _job: True)
    monkeypatch.setattr("app.core.job_lock.advisory_lock", _lock)

    def _run(tenant_id=None, schedule_type=None):
        calls.append((tenant_id, schedule_type))
        return {"signals_checked": 0, "leads_created": 0, "scores_updated": 0}

    monkeypatch.setattr("app.services.intent_engine.run_intent_engine", _run)
    return scheduler


@pytest.mark.parametrize("job", ["job_intent_signals_daily", "job_intent_signals_weekly"])
def test_scheduled_intent_scan_skipped_without_credits(db_session, test_tenant, monkeypatch, job):
    _enforce(monkeypatch)
    _set_available(db_session, test_tenant.tenant_id, 2)
    calls = []
    scheduler = _intent_scheduler(monkeypatch, test_tenant.tenant_id, calls)
    getattr(scheduler, job)()
    assert calls == []


@pytest.mark.parametrize("job", ["job_intent_signals_daily", "job_intent_signals_weekly"])
def test_scheduled_intent_scan_runs_with_credits(db_session, test_tenant, monkeypatch, job):
    _enforce(monkeypatch)
    _set_available(db_session, test_tenant.tenant_id, 500)
    calls = []
    scheduler = _intent_scheduler(monkeypatch, test_tenant.tenant_id, calls)
    getattr(scheduler, job)()
    assert [c[0] for c in calls] == [test_tenant.tenant_id]
