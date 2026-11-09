"""Strict fetch budget: a run asked for N jobs never pulls more than N from the APIs.

Each job-board adapter sizes every request to what is left (Fantastic.jobs `limit`,
TheirStack `limit`, Adzuna `results_per_page`, JSearch whole pages of 10), and the
pipeline runs sources one at a time against one shared budget. See
`Plan_Lead_Sourcing_Cap.md` (follow-up 2).
"""
import pytest

from app.services.adapters.base import JobSourceAdapter
from app.services.adapters.job_sources.adzuna import AdzunaAdapter
from app.services.adapters.job_sources.fantastic_jobs import FantasticJobsAdapter
from app.services.adapters.job_sources.jsearch import JSearchAdapter
from app.services.adapters.job_sources.theirstack import TheirStackAdapter
from app.services.pipelines import lead_sourcing
from tests.unit.test_loopholes_pipelines import _tenant, _use_test_session

pytestmark = pytest.mark.unit

TITLES = [f"Title {i}" for i in range(12)]  # several title batches per adapter


# ---------------------------------------------------------------------------
# A fake job API: returns exactly as many results as each request asks for,
# from a large pool, and records every request.
# ---------------------------------------------------------------------------

class _FakeApi:
    def __init__(self, size_of):
        self.size_of = size_of  # request -> how many results it asked for
        self.requests = []
        self.returned = 0

    def respond(self, request, key):
        n = self.size_of(request)
        self.requests.append(n)
        self.returned += n
        return {key: [{"i": self.returned - n + k} for k in range(n)]}


def _patch_http(monkeypatch, module, api, key, method):
    class _Resp:
        status_code = 200

        def __init__(self, body):
            self._body = body

        def json(self):
            return self._body[key] if key is None else self._body

        def raise_for_status(self):
            return None

    class _Client:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url, params=None, **k):
            return _Resp(api.respond({"params": params or {}}, key))

        def post(self, url, json=None, **k):
            return _Resp(api.respond({"json": json or {}}, key))

    monkeypatch.setattr(f"app.services.adapters.job_sources.{module}.httpx.Client", _Client)


def _keep_everything(monkeypatch, adapter):
    monkeypatch.setattr(adapter, "normalize", lambda raw: {"client_name": f"Co {raw['i']}",
                                                         "job_title": "HR Manager"})
    monkeypatch.setattr(adapter, "filter_excluded", lambda *a, **k: False)


# ---------------------------------------------------------------------------
# page_plan
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("remaining,size,pages,expected", [
    (10, 25, 10, (10, 1)),
    (35, 25, 10, (17, 2)),     # never over: 34
    (50, 50, 10, (50, 1)),
    (120, 50, 10, (40, 3)),
    (5000, 50, 10, (50, 10)),  # bounded by max_pages
    (0, 25, 10, (0, 0)),
    (7, 25, 0, (0, 0)),
])
def test_page_plan_never_exceeds_remaining(remaining, size, pages, expected):
    plan = JobSourceAdapter.page_plan(remaining, size, pages)
    assert plan == expected
    assert plan[0] * plan[1] <= remaining


# ---------------------------------------------------------------------------
# Each adapter, against a fake API
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("limit", [10, 35, 250])
def test_fantastic_jobs_asks_only_for_what_is_left(monkeypatch, limit):
    api = _FakeApi(lambda r: r["params"]["limit"])
    _patch_http(monkeypatch, "fantastic_jobs", api, None, "get")
    a = FantasticJobsAdapter(api_key="k")
    _keep_everything(monkeypatch, a)

    jobs = a.fetch_jobs(job_titles=TITLES, limit=limit, tuning={"max_pages": 20})

    assert api.returned == a._raw_returned == len(jobs) == limit
    assert all(n <= FantasticJobsAdapter.PAGE_SIZE for n in api.requests)


def test_fantastic_jobs_ten_is_one_request_of_ten(monkeypatch):
    api = _FakeApi(lambda r: r["params"]["limit"])
    _patch_http(monkeypatch, "fantastic_jobs", api, None, "get")
    a = FantasticJobsAdapter(api_key="k")
    _keep_everything(monkeypatch, a)

    a.fetch_jobs(job_titles=TITLES, limit=10, tuning={"max_pages": 20})

    assert api.requests == [10]  # not 20 pages of 100


@pytest.mark.parametrize("limit", [10, 35, 250])
def test_theirstack_never_returns_more_than_limit(monkeypatch, limit):
    api = _FakeApi(lambda r: r["json"]["limit"])
    _patch_http(monkeypatch, "theirstack", api, "data", "post")
    a = TheirStackAdapter(api_key="k")
    _keep_everything(monkeypatch, a)

    a.fetch_jobs(job_titles=TITLES, limit=limit, tuning={"batch_size": 4})

    assert api.returned == a._raw_returned
    assert limit - len(api.requests) < api.returned <= limit


@pytest.mark.parametrize("limit", [10, 35, 250])
def test_adzuna_never_returns_more_than_limit(monkeypatch, limit):
    api = _FakeApi(lambda r: r["params"]["results_per_page"])
    _patch_http(monkeypatch, "adzuna", api, "results", "get")
    a = AdzunaAdapter(app_id="id", api_key="k")
    _keep_everything(monkeypatch, a)

    a.fetch_jobs(job_titles=TITLES, limit=limit)

    assert api.returned == a._raw_returned
    assert limit - len(api.requests) < api.returned <= limit


@pytest.mark.parametrize("limit,expected", [(10, 10), (35, 30), (250, 250), (9, 0)])
def test_jsearch_fetches_whole_pages_within_limit(monkeypatch, limit, expected):
    api = _FakeApi(lambda r: int(r["params"]["num_pages"]) * JSearchAdapter.RESULTS_PER_PAGE)
    _patch_http(monkeypatch, "jsearch", api, "data", "get")
    a = JSearchAdapter(api_key="k")
    _keep_everything(monkeypatch, a)

    a.fetch_jobs(job_titles=TITLES, limit=limit)

    # Pages of 10 can't be shrunk, so a remainder under 10 is left unfetched.
    assert api.returned == a._raw_returned == expected


# ---------------------------------------------------------------------------
# The pipeline: one shared budget across all sources
# ---------------------------------------------------------------------------

class _Source:
    """A job source with `available` jobs that honours `limit` (or not)."""

    def __init__(self, name, available, overshoot=0):
        self.name, self.available, self.overshoot = name, available, overshoot
        self.limits = []

    def fetch_jobs(self, limit=1000, **kw):
        self.limits.append(limit)
        n = min(limit + self.overshoot, self.available)
        self._raw_returned = n
        return [{"client_name": f"{self.name} {i}", "job_title": "HR Manager", "state": "TX",
                 "job_link": f"https://{self.name}.example/{i}", "source": self.name}
                for i in range(n)]


def _patch_pipeline(monkeypatch, db_session, sources):
    _use_test_session(monkeypatch, lead_sourcing, db_session)
    monkeypatch.setattr(lead_sourcing, "get_all_job_source_adapters",
                        lambda db, tenant_id=None: [(s.name, s) for s in sources])
    monkeypatch.setattr(lead_sourcing, "get_lob_lead_source_adapters",
                        lambda db, tenant_id=None, lob_id=None: [])
    monkeypatch.setattr(lead_sourcing, "_partition_tiers", lambda adapters, tier_map: (adapters, []))
    monkeypatch.setattr(lead_sourcing, "deduplicate_jobs", lambda all_jobs, db, tenant_id=None: list(all_jobs))
    monkeypatch.setattr(lead_sourcing, "_apply_freshness_gate", lambda jobs_, counters, **kw: jobs_)
    monkeypatch.setattr(lead_sourcing, "_apply_company_gate", lambda db, jobs_, counters, **kw: jobs_)
    monkeypatch.setattr(lead_sourcing, "export_leads_to_xlsx", lambda db, filepath=None: None)


def _run(tenant_id, **kw):
    return lead_sourcing.run_lead_sourcing_pipeline(["mock"], triggered_by="test", tenant_id=tenant_id, **kw)


def test_budget_is_shared_and_later_sources_never_run(db_session, monkeypatch):
    t = _tenant(db_session, "budget-a")
    a, b, c = _Source("a", 6), _Source("b", 100), _Source("c", 100)
    _patch_pipeline(monkeypatch, db_session, [a, b, c])

    result = _run(t.tenant_id, max_leads=10)

    assert a.limits == [10]
    assert b.limits == [4]          # only what a left over
    assert c.limits == []           # budget used up — never called
    assert result["jobs_fetched"] == 10
    assert result["inserted"] == 10


def test_budget_truncates_a_source_that_ignores_its_limit(db_session, monkeypatch):
    t = _tenant(db_session, "budget-b")
    greedy = _Source("greedy", 500, overshoot=90)
    _patch_pipeline(monkeypatch, db_session, [greedy])

    result = _run(t.tenant_id, max_leads=10)

    assert result["inserted"] == 10  # never more than asked, even if the API overshoots
    assert result["jobs_fetched"] == 100  # reported honestly


def test_fetch_limit_reached_when_jobs_are_lost_to_filters(db_session, monkeypatch):
    t = _tenant(db_session, "budget-c")
    a = _Source("a", 100)
    _patch_pipeline(monkeypatch, db_session, [a])
    # The gates drop 6 of the 10 fetched (duplicates / out-of-scope companies).
    monkeypatch.setattr(lead_sourcing, "_apply_company_gate", lambda db, jobs_, counters, **kw: jobs_[:4])

    result = _run(t.tenant_id, max_leads=10)

    assert result["jobs_fetched"] == 10
    assert result["inserted"] == 4
    assert result["stopped_reason"] == "fetch_limit_reached"


def test_no_budget_keeps_parallel_fetch(db_session, monkeypatch):
    t = _tenant(db_session, "budget-d")
    a, b = _Source("a", 30), _Source("b", 30)
    _patch_pipeline(monkeypatch, db_session, [a, b])

    result = _run(t.tenant_id)

    assert a.limits == [1000] and b.limits == [1000]  # pipeline_adapter_limit default
    assert result["inserted"] == 60
    assert result["stopped_reason"] is None
