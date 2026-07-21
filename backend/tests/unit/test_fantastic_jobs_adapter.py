"""Unit tests for the Fantastic.jobs adapter + its pipeline wiring."""
import pytest

from app.services.adapters.job_sources.fantastic_jobs import FantasticJobsAdapter
from app.services.pipelines.lead_sourcing import SOURCE_TIERS, SOURCE_COST_RANK

pytestmark = pytest.mark.unit


def test_fetch_jobs_accepts_pipeline_contract():
    """fetch_from_source calls adapter.fetch_jobs(..., limit=, tuning=) — the
    adapter must accept that signature. Unconfigured → returns [] (no HTTP)."""
    a = FantasticJobsAdapter(api_key="")  # not configured
    a._exclude_title = ["intern"]
    a._push_negatives = True
    jobs = a.fetch_jobs(
        location="United States",
        posted_within_days=7,
        industries=["Construction"],
        exclude_keywords=["staffing"],
        job_titles=["HR Manager"],
        limit=1000,
        tuning={"max_pages": 3, "max_employee_count": 200},
    )
    assert jobs == []


def test_is_configured_and_host_default():
    assert FantasticJobsAdapter(api_key="").is_configured() is False
    assert FantasticJobsAdapter(api_key="k").is_configured() is True
    assert FantasticJobsAdapter(api_key="k").host == "data.fantastic.jobs"


def test_normalize_maps_company_fields():
    a = FantasticJobsAdapter(api_key="k")
    raw = {
        "id": 123, "title": "HR Manager", "organization": "Acme Co",
        "organization_url": "https://linkedin.com/company/acme",
        "org_linkedin_website": "https://acme.com",
        "org_linkedin_industry": "Construction",
        "org_linkedin_headcount": 85,
        "org_linkedin_recruitment_agency_derived": False,
        "date_posted": "2026-07-20T10:00:00",
        "locations_derived": ["Dallas, Texas, United States"],
        "cities_derived": ["Dallas"],
        "ai_salary_min_value": 60000, "ai_salary_max_value": 80000,
        "url": "https://linkedin.com/jobs/view/1",
        "recruiter_name": "Jane Poster",
    }
    n = a.normalize(raw)
    assert n["client_name"] == "Acme Co"
    assert n["job_title"] == "HR Manager"
    assert n["state"] == "TX"
    assert n["company_size"] == "85"
    assert n["employee_count"] == 85
    assert n["industry"] == "Construction"
    assert n["is_staffing_agency"] is False
    assert n["salary_min"] == 60000
    assert n["source"] == "fantastic_jobs"
    assert n["recruiter_name"] == "Jane Poster"


def test_registered_in_source_tiers():
    assert SOURCE_TIERS.get("fantastic_jobs") == 1        # always-run tier
    assert "fantastic_jobs" in SOURCE_COST_RANK            # has a run-order rank


@pytest.mark.parametrize("hours,days,expected", [
    (1, 7, "1h"),      # explicit 1-hour window
    (24, 7, "24h"),    # explicit 24-hour window
    (48, 7, "7d"),     # >24h hours → 7d bucket
    (0, 1, "24h"),     # no hours, 1 day → 24h
    (0, 7, "7d"),      # no hours, 7 days → 7d
])
def test_time_frame_maps_from_hours_or_days(monkeypatch, hours, days, expected):
    captured = {}

    class _Resp:
        status_code = 200
        def json(self):
            return []  # empty → single page, no results needed

    class _Client:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def get(self, url, params=None, headers=None, timeout=None):
            captured.update(params or {})
            return _Resp()

    monkeypatch.setattr(
        "app.services.adapters.job_sources.fantastic_jobs.httpx.Client", _Client
    )
    a = FantasticJobsAdapter(api_key="k")
    a._posted_within_hours = hours
    a.fetch_jobs(posted_within_days=days, limit=100, tuning={"max_pages": 1})
    assert captured["time_frame"] == expected


def _capture_client(monkeypatch, captured):
    class _Resp:
        status_code = 200
        def json(self):
            return []

    class _Client:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def get(self, url, params=None, headers=None, timeout=None):
            captured.update(params or {})
            return _Resp()

    monkeypatch.setattr(
        "app.services.adapters.job_sources.fantastic_jobs.httpx.Client", _Client
    )


def test_size_ceiling_auto_follows_gate_when_tuning_unset(monkeypatch):
    """No max_employee_count in tuning → server-side ceiling follows the ICP
    gate value the pipeline sets (_max_employee_count_gate)."""
    captured = {}
    _capture_client(monkeypatch, captured)
    a = FantasticJobsAdapter(api_key="k")
    a._max_employee_count_gate = 350
    a.fetch_jobs(posted_within_days=1, limit=100, tuning={"max_pages": 1})
    assert captured["organization_headcount_lt"] == 351  # gate 350 + 1


def test_size_ceiling_tuning_override_wins_over_gate(monkeypatch):
    """An explicit per-adapter tuning value overrides the gate."""
    captured = {}
    _capture_client(monkeypatch, captured)
    a = FantasticJobsAdapter(api_key="k")
    a._max_employee_count_gate = 350
    a.fetch_jobs(posted_within_days=1, limit=100, tuning={"max_pages": 1, "max_employee_count": 150})
    assert captured["organization_headcount_lt"] == 151  # override 150 + 1


def test_fetch_jobs_omits_ats_only_param(monkeypatch):
    """active-jb rejects include_basic_organization_details (active-ats only)
    with HTTP 400 — regression: it must NEVER appear in the query, and the
    server-side size bounds must be present. Org fields are always-on on JB."""
    captured = {}

    class _Resp:
        status_code = 200
        def json(self):  # one page then stop (len < 100)
            return [{"id": 1, "organization": "Acme", "org_linkedin_headcount": 50}]

    class _Client:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def get(self, url, params=None, headers=None, timeout=None):
            captured.update(params or {})
            return _Resp()

    monkeypatch.setattr(
        "app.services.adapters.job_sources.fantastic_jobs.httpx.Client", _Client
    )
    a = FantasticJobsAdapter(api_key="k")
    jobs = a.fetch_jobs(location="United States", posted_within_days=1, limit=100,
                        tuning={"max_pages": 1, "max_employee_count": 200})
    assert jobs and jobs[0]["client_name"] == "Acme"
    assert "include_basic_organization_details" not in captured
    assert captured["organization_headcount_lt"] == 201
    assert captured["time_frame"] == "24h"
