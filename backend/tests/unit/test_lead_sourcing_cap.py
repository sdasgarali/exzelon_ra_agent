"""Lead-sourcing per-run cap (`max_leads`) and the stop when credits run out.

See `Plan_Lead_Sourcing_Cap.md`. A run saves at most the requested number of leads,
scales its paid company research to that request, and stops as soon as the
workspace can't pay for the next lead instead of spending into an overage.
"""
import pytest

from app.core.credit_costs import estimate_run_credits
from app.core.settings_resolver import set_tenant_setting
from app.services.credit_metering import affordable_quantity, get_balance, spend
from app.services.pipelines import lead_sourcing
from app.services.pipelines.lead_sourcing import (
    MAX_LEADS_PER_RUN_LIMIT, MIN_LEADS_PER_RUN, resolve_max_leads,
)
from tests.unit.test_loopholes_credits import _enforce, _pipeline_headers, _set_available
from tests.unit.test_loopholes_pipelines import (
    _billed, _cost, _patch_sourcing, _source_jobs, _tenant,
)

pytestmark = pytest.mark.unit


def _run(tenant_id, **kw):
    return lead_sourcing.run_lead_sourcing_pipeline(["mock"], triggered_by="test",
                                                    tenant_id=tenant_id, **kw)


def _stored(db, tenant_id):
    from app.db.models.lead import LeadDetails
    db.expire_all()
    return db.query(LeadDetails).filter(LeadDetails.tenant_id == tenant_id).count()


# ---------------------------------------------------------------------------
# resolve_max_leads
# ---------------------------------------------------------------------------

def test_resolve_max_leads_prefers_request_then_setting(db_session):
    t = _tenant(db_session, "cap-resolve")
    assert resolve_max_leads(db_session, t.tenant_id) is None  # no setting = no cap
    assert resolve_max_leads(db_session, t.tenant_id, 25) == 25

    set_tenant_setting(db_session, "lead_sourcing_max_leads_per_run", 40, tenant_id=t.tenant_id)
    db_session.commit()
    assert resolve_max_leads(db_session, t.tenant_id) == 40
    assert resolve_max_leads(db_session, t.tenant_id, 12) == 12
    # Below the minimum is raised to it.
    assert resolve_max_leads(db_session, t.tenant_id, 7) == MIN_LEADS_PER_RUN

    set_tenant_setting(db_session, "lead_sourcing_max_leads_per_run", 99_999, tenant_id=t.tenant_id)
    db_session.commit()
    assert resolve_max_leads(db_session, t.tenant_id) == MAX_LEADS_PER_RUN_LIMIT

    set_tenant_setting(db_session, "lead_sourcing_max_leads_per_run", 0, tenant_id=t.tenant_id)
    db_session.commit()
    assert resolve_max_leads(db_session, t.tenant_id) is None


def test_estimate_uses_the_cap():
    per_lead = estimate_run_credits("lead_sourcing", units=1)
    assert estimate_run_credits("lead_sourcing", units=10) == 10 * per_lead
    # Never more than the documented 50-lead minimum.
    assert estimate_run_credits("lead_sourcing", units=1_000) == estimate_run_credits("lead_sourcing")


# ---------------------------------------------------------------------------
# The cap
# ---------------------------------------------------------------------------

def test_run_saves_at_most_max_leads(db_session, monkeypatch):
    t = _tenant(db_session, "cap-a")
    _patch_sourcing(monkeypatch, db_session, _source_jobs(25))

    result = _run(t.tenant_id, max_leads=10)

    assert _stored(db_session, t.tenant_id) == 10
    assert result["inserted"] == 10
    assert result["stopped_reason"] == "max_leads_reached"
    assert result["leads_not_saved"] == 15
    assert result["requested_max_leads"] == 10
    assert _billed(db_session, t.tenant_id, "lead_sourced") == _cost(db_session, "lead_sourced", 10)


def test_run_uses_workspace_default_cap(db_session, monkeypatch):
    t = _tenant(db_session, "cap-b")
    set_tenant_setting(db_session, "lead_sourcing_max_leads_per_run", 10, tenant_id=t.tenant_id)
    db_session.commit()
    _patch_sourcing(monkeypatch, db_session, _source_jobs(15))

    result = _run(t.tenant_id)

    assert _stored(db_session, t.tenant_id) == 10
    assert result["stopped_reason"] == "max_leads_reached"


def test_no_cap_and_no_enforcement_runs_to_the_end(db_session, monkeypatch):
    t = _tenant(db_session, "cap-c")
    _patch_sourcing(monkeypatch, db_session, _source_jobs(15))

    result = _run(t.tenant_id)

    assert _stored(db_session, t.tenant_id) == 15
    assert result["stopped_reason"] is None
    assert result["leads_not_saved"] == 0


def test_cap_larger_than_candidates_is_not_reported_as_reached(db_session, monkeypatch):
    t = _tenant(db_session, "cap-d")
    _patch_sourcing(monkeypatch, db_session, _source_jobs(4))

    result = _run(t.tenant_id, max_leads=10)

    assert result["inserted"] == 4
    assert result["stopped_reason"] is None


# ---------------------------------------------------------------------------
# Out of credits
# ---------------------------------------------------------------------------

def test_run_stops_when_credits_run_out(db_session, monkeypatch):
    t = _tenant(db_session, "credit-a")
    _enforce(monkeypatch)
    _set_available(db_session, t.tenant_id, 12)
    _patch_sourcing(monkeypatch, db_session, _source_jobs(30))

    result = _run(t.tenant_id, max_leads=100)

    assert _stored(db_session, t.tenant_id) == 12
    assert result["stopped_reason"] == "credits_exhausted"
    assert result["leads_not_saved"] == 18
    assert _billed(db_session, t.tenant_id, "lead_sourced") == _cost(db_session, "lead_sourced", 12)
    db_session.expire_all()
    assert get_balance(db_session, t.tenant_id).total_available >= 0


def test_run_rechecks_balance_when_another_pipeline_spends(db_session, monkeypatch):
    t = _tenant(db_session, "credit-b")
    _enforce(monkeypatch)
    _set_available(db_session, t.tenant_id, 30)
    _patch_sourcing(monkeypatch, db_session, _source_jobs(30))
    calls = {"n": 0}

    def _check_cancel(run_id, db):
        calls["n"] += 1
        if calls["n"] == 5:  # mid-way through the first batch, another run spends 15
            spend(db, t.tenant_id, "lead_sourced", 15, commit=True)
        return False
    monkeypatch.setattr(lead_sourcing, "check_cancel", _check_cancel)

    result = _run(t.tenant_id)

    # 30 credits - 15 spent elsewhere = 15 leads, caught at the idx-10 checkpoint.
    assert result["inserted"] == 15
    assert result["stopped_reason"] == "credits_exhausted"
    db_session.expire_all()
    assert get_balance(db_session, t.tenant_id).total_available >= 0


def test_enforcement_off_ignores_balance(db_session, monkeypatch):
    t = _tenant(db_session, "credit-c")
    _set_available(db_session, t.tenant_id, 2)
    _patch_sourcing(monkeypatch, db_session, _source_jobs(8))

    result = _run(t.tenant_id)

    assert result["inserted"] == 8
    assert result["stopped_reason"] is None


# ---------------------------------------------------------------------------
# Paid research is scaled to the request and the balance
# ---------------------------------------------------------------------------

def _record_company_gate(monkeypatch, seen):
    def _gate(db, jobs_, counters, **kw):
        seen.update(kw)
        return jobs_
    monkeypatch.setattr(lead_sourcing, "_apply_company_gate", _gate)


def test_company_research_scales_with_max_leads(db_session, monkeypatch):
    t = _tenant(db_session, "research-a")
    _patch_sourcing(monkeypatch, db_session, _source_jobs(3))
    seen = {}
    _record_company_gate(monkeypatch, seen)

    _run(t.tenant_id, max_leads=10)

    assert seen["enrich_max_companies"] == 10 * lead_sourcing.FIRMOGRAPHIC_LOOKUPS_PER_REQUESTED_LEAD


def test_company_research_is_not_limited_by_credits(db_session, monkeypatch):
    # Research isn't billed to the workspace any more, so its balance doesn't cap it.
    t = _tenant(db_session, "research-b")
    _enforce(monkeypatch)
    _set_available(db_session, t.tenant_id, 100)
    _patch_sourcing(monkeypatch, db_session, _source_jobs(3))
    seen = {}
    _record_company_gate(monkeypatch, seen)

    _run(t.tenant_id)

    from app.core.config import settings
    assert seen["enrich_max_companies"] == settings.LEAD_SOURCING_ENRICH_MAX_COMPANIES


def test_company_gate_research_is_not_billed(db_session, monkeypatch):
    from app.services import company_enrichment
    seen = {}

    def _resolve(db, companies, **kw):
        seen.update(kw)
        return {}
    monkeypatch.setattr(company_enrichment, "resolve_company_metadata_batch", _resolve)

    lead_sourcing._apply_company_gate(
        db_session, [{"client_name": "Acme Bakery", "job_title": "HR Manager"}], {},
        tenant_id=1, enrich=True,
    )

    assert seen["bill_tenant"] is False


def test_applicant_scrape_is_not_billed(db_session, monkeypatch):
    from app.services import applicant_enrichment
    seen = {}

    def _resolve(db, jobs, api_key, **kw):
        seen.update(kw)
        return {}
    monkeypatch.setattr(applicant_enrichment, "resolve_applicant_counts", _resolve)

    lead_sourcing._apply_applicant_gate(
        db_session, [{"job_link": "https://www.linkedin.com/jobs/view/1"}], {},
        api_key="k", tenant_id=1,
    )

    assert seen["bill_tenant"] is False


def test_affordable_quantity(db_session, monkeypatch):
    t = _tenant(db_session, "afford")
    _set_available(db_session, t.tenant_id, 10)
    assert affordable_quantity(db_session, t.tenant_id, "lead_sourced") is None  # not enforced
    _enforce(monkeypatch)
    assert affordable_quantity(db_session, t.tenant_id, "lead_sourced") == 10
    assert affordable_quantity(db_session, t.tenant_id, "firmographic_lookup") == 3
    assert affordable_quantity(db_session, t.tenant_id, "lead_sourced", share=0.5) == 5
    assert affordable_quantity(db_session, None, "lead_sourced") is None
    _set_available(db_session, t.tenant_id, -5)
    assert affordable_quantity(db_session, t.tenant_id, "lead_sourced") == 0


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

def test_endpoint_small_run_needs_only_its_own_credits(client, db_session, test_tenant, sa_headers, monkeypatch):
    h = _pipeline_headers(db_session, test_tenant, sa_headers, monkeypatch, credits=10)
    captured = {}
    monkeypatch.setattr(lead_sourcing, "run_lead_sourcing_pipeline", lambda **k: captured.update(k) or {})

    # Without a cap the gate still asks for the 50-lead minimum.
    assert client.post("/api/v1/pipelines/lead-sourcing/run", headers=h).status_code == 402

    r = client.post("/api/v1/pipelines/lead-sourcing/run", headers=h, params={"max_leads": 10})
    assert r.status_code == 200, r.text
    assert r.json()["max_leads"] == 10
    assert captured["max_leads"] == 10

    assert client.post("/api/v1/pipelines/lead-sourcing/run", headers=h,
                       params={"max_leads": 11}).status_code == 402


@pytest.mark.parametrize("bad", [0, -1, MIN_LEADS_PER_RUN - 1, MAX_LEADS_PER_RUN_LIMIT + 1])
def test_endpoint_rejects_out_of_range_cap(client, db_session, test_tenant, sa_headers, monkeypatch, bad):
    h = _pipeline_headers(db_session, test_tenant, sa_headers, monkeypatch, credits=500)
    r = client.post("/api/v1/pipelines/lead-sourcing/run", headers=h, params={"max_leads": bad})
    assert r.status_code == 422


def test_run_options_endpoint(client, db_session, test_tenant, sa_headers, monkeypatch):
    h = _pipeline_headers(db_session, test_tenant, sa_headers, monkeypatch, credits=40)
    set_tenant_setting(db_session, "lead_sourcing_max_leads_per_run", 25, tenant_id=test_tenant.tenant_id)
    db_session.commit()

    r = client.get("/api/v1/pipelines/lead-sourcing/run-options", headers=h)

    assert r.status_code == 200, r.text
    assert r.json() == {"default_max_leads": 25, "min_leads": MIN_LEADS_PER_RUN,
                        "max_leads_limit": MAX_LEADS_PER_RUN_LIMIT,
                        "credits_per_lead": 1.0, "affordable_leads": 40}


# ---------------------------------------------------------------------------
# Default set from the Run dialog
# ---------------------------------------------------------------------------

def test_run_dialog_can_save_and_clear_the_default(client, db_session, test_tenant, sa_headers, monkeypatch):
    h = _pipeline_headers(db_session, test_tenant, sa_headers, monkeypatch, credits=500)
    url = "/api/v1/pipelines/lead-sourcing/default-max-leads"

    r = client.put(url, headers=h, json={"max_leads": 30})
    assert r.status_code == 200, r.text
    assert r.json() == {"default_max_leads": 30}
    db_session.expire_all()
    assert resolve_max_leads(db_session, test_tenant.tenant_id) == 30
    opts = client.get("/api/v1/pipelines/lead-sourcing/run-options", headers=h).json()
    assert opts["default_max_leads"] == 30

    r = client.put(url, headers=h, json={"max_leads": None})
    assert r.status_code == 200
    db_session.expire_all()
    assert resolve_max_leads(db_session, test_tenant.tenant_id) is None


@pytest.mark.parametrize("bad", [0, -2, MIN_LEADS_PER_RUN - 1, MAX_LEADS_PER_RUN_LIMIT + 1])
def test_default_rejects_out_of_range(client, db_session, test_tenant, sa_headers, monkeypatch, bad):
    h = _pipeline_headers(db_session, test_tenant, sa_headers, monkeypatch, credits=500)
    r = client.put("/api/v1/pipelines/lead-sourcing/default-max-leads", headers=h, json={"max_leads": bad})
    assert r.status_code == 422


def test_default_needs_a_workspace(client, sa_headers):
    # A super admin who hasn't picked a workspace must not write a global default.
    r = client.put("/api/v1/pipelines/lead-sourcing/default-max-leads", headers=sa_headers,
                   json={"max_leads": 30})
    assert r.status_code == 400


def test_default_is_per_workspace(client, db_session, test_tenant, sa_headers, monkeypatch):
    other = _tenant(db_session, "other-ws")
    h = _pipeline_headers(db_session, test_tenant, sa_headers, monkeypatch, credits=500)
    client.put("/api/v1/pipelines/lead-sourcing/default-max-leads", headers=h, json={"max_leads": 30})
    db_session.expire_all()
    assert resolve_max_leads(db_session, other.tenant_id) is None


def test_viewer_cannot_change_the_default(client, viewer_token):
    r = client.put("/api/v1/pipelines/lead-sourcing/default-max-leads",
                   headers={"Authorization": f"Bearer {viewer_token}"}, json={"max_leads": 30})
    assert r.status_code == 403
