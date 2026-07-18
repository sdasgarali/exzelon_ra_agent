"""Unit tests for applicant enrichment + the pipeline high-applicant gate.

No network: the Firecrawl scraper and cost hook are monkeypatched.
"""
import pytest

import app.services.applicant_enrichment as ae
from app.services.applicant_enrichment import resolve_applicant_counts
from app.services.pipelines import lead_sourcing as ls

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _no_cost(monkeypatch):
    # record_pipeline_cost is imported lazily inside resolve_applicant_counts.
    import app.services.cost_tracker as ct
    monkeypatch.setattr(ct, "record_pipeline_cost", lambda *a, **k: None)


class TestResolveApplicantCounts:
    def test_scrapes_only_linkedin_indeed_and_parses(self, monkeypatch):
        pages = {
            "https://www.linkedin.com/jobs/view/1": "Over 100 applicants",
            "https://www.indeed.com/viewjob?jk=2": "12 applicants",
            "https://www.linkedin.com/jobs/view/3": "no count here",
        }
        monkeypatch.setattr(ae, "scrape_markdown", lambda url, key, timeout=20: pages.get(url))

        jobs = [
            {"job_link": "https://www.linkedin.com/jobs/view/1"},
            {"job_link": "https://www.indeed.com/viewjob?jk=2"},
            {"job_link": "https://www.linkedin.com/jobs/view/3"},  # scraped, no count → absent
            {"job_link": "https://boards.greenhouse.io/x/jobs/9"},  # not scrapable → skipped
            {"job_link": ""},                                       # no url → skipped
        ]
        out = resolve_applicant_counts(None, jobs, api_key="fc-key", max_lookups=50)
        assert out.get(id(jobs[0])) == 101
        assert out.get(id(jobs[1])) == 12
        assert id(jobs[2]) not in out
        assert id(jobs[3]) not in out

    def test_respects_lookup_cap(self, monkeypatch):
        calls = {"n": 0}

        def _fake(url, key, timeout=20):
            calls["n"] += 1
            return "50 applicants"

        monkeypatch.setattr(ae, "scrape_markdown", _fake)
        jobs = [{"job_link": f"https://www.linkedin.com/jobs/view/{i}"} for i in range(5)]
        resolve_applicant_counts(None, jobs, api_key="k", max_lookups=2)
        assert calls["n"] == 2

    def test_no_key_no_scrape(self, monkeypatch):
        monkeypatch.setattr(ae, "scrape_markdown", lambda *a, **k: "999 applicants")
        jobs = [{"job_link": "https://www.linkedin.com/jobs/view/1"}]
        assert resolve_applicant_counts(None, jobs, api_key="", max_lookups=50) == {}


class TestApplicantGate:
    def test_drops_over_threshold_keeps_rest(self, monkeypatch):
        jobs = [
            {"job_title": "hot", "_c": 150},
            {"job_title": "ok", "_c": 40},
            {"job_title": "unknown"},  # no resolved count → kept
        ]
        # Patch the enrichment resolver the gate calls (imported lazily inside it).
        monkeypatch.setattr(
            ae, "resolve_applicant_counts",
            lambda db, js, api_key, **k: {id(j): j["_c"] for j in js if "_c" in j},
        )
        counters = {}
        kept = ls._apply_applicant_gate(
            None, jobs, counters, api_key="k", max_applicants=100, max_lookups=50,
        )
        titles = {j["job_title"] for j in kept}
        assert titles == {"ok", "unknown"}
        assert counters["excluded_high_applicants"] == 1

    def test_disabled_threshold_is_noop(self, monkeypatch):
        jobs = [{"job_title": "hot", "_c": 9999}]
        monkeypatch.setattr(
            ae, "resolve_applicant_counts",
            lambda db, js, api_key, **k: {id(j): j["_c"] for j in js if "_c" in j},
        )
        counters = {}
        kept = ls._apply_applicant_gate(None, jobs, counters, api_key="k", max_applicants=0)
        assert len(kept) == 1
        assert counters["excluded_high_applicants"] == 0
