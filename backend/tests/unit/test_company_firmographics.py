"""Unit tests for the Apollo-backed firmographic enrichment module.

Firmographic size is the piece the free LLM resolver can't do — these tests lock
in: domain-keyed lookups, the cost-guard cap, domain-less skipping, provider/key
gating, and that the sourcing resolver fills company_size from a (mocked) Apollo
response while the free_only gate path never triggers a paid lookup.
"""
import pytest

from app.services import company_firmographics as cf

pytestmark = pytest.mark.unit


# --- tiny httpx stubs (no network) ------------------------------------------
class _Resp:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload

    def json(self):
        return self._payload


class _Http:
    """Records calls; returns a queued response per domain."""
    def __init__(self, by_domain):
        self.by_domain = by_domain
        self.calls = []

    def post(self, url, params=None, headers=None, timeout=None):
        dom = (params or {}).get("domain")
        self.calls.append(dom)
        return self.by_domain.get(dom, _Resp(404, {}))

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _org(emp=None, industry=None, site=None):
    return _Resp(200, {"organization": {
        "estimated_num_employees": emp, "industry": industry, "website_url": site,
    }})


class TestEmployeeCountToSize:
    @pytest.mark.parametrize("count,expected", [
        (10, "1-50"), (50, "1-50"), (120, "51-200"), (500, "201-500"),
        (900, "501-1000"), (3000, "1001-5000"), (9000, "5000+"),
    ])
    def test_buckets(self, count, expected):
        assert cf.employee_count_to_size(count) == expected


class TestApolloEnrichByDomain:
    def test_success_maps_fields(self):
        http = _Http({"acme.com": _org(emp=510, industry="construction", site="http://acme.com")})
        out = cf.apollo_enrich_by_domain(http, "key", "acme.com")
        assert out["employee_count"] == 510
        assert out["company_size"] == "501-1000"
        assert out["industry"] == "construction"
        assert out["website"] == "http://acme.com"

    def test_unknown_company_404(self):
        http = _Http({})
        assert cf.apollo_enrich_by_domain(http, "key", "nope.com") is None

    def test_no_domain_or_key_short_circuits(self):
        http = _Http({})
        assert cf.apollo_enrich_by_domain(http, "key", "") is None
        assert cf.apollo_enrich_by_domain(http, "", "acme.com") is None
        assert http.calls == []  # never hit the wire

    def test_missing_employee_count_leaves_size_none(self):
        http = _Http({"acme.com": _org(emp=None, industry="retail")})
        out = cf.apollo_enrich_by_domain(http, "key", "acme.com")
        assert out["industry"] == "retail"
        assert out["employee_count"] is None
        assert out["company_size"] is None


class TestEnrichFirmographicsBatch:
    def _enable_apollo(self, monkeypatch, http):
        monkeypatch.setattr(cf, "get_firmographic_provider", lambda db, tenant_id=None: "apollo")
        monkeypatch.setattr(cf, "_get_apollo_key", lambda db, tenant_id=None: "key")
        monkeypatch.setattr(cf.httpx, "Client", lambda *a, **k: http)

    def test_disabled_provider_is_noop(self, db_session, monkeypatch):
        monkeypatch.setattr(cf, "get_firmographic_provider", lambda db, tenant_id=None: "none")
        assert cf.enrich_firmographics_batch(db_session, [("Acme", "acme.com")]) == {}

    def test_no_key_is_noop(self, db_session, monkeypatch):
        monkeypatch.setattr(cf, "get_firmographic_provider", lambda db, tenant_id=None: "apollo")
        monkeypatch.setattr(cf, "_get_apollo_key", lambda db, tenant_id=None: "")
        assert cf.enrich_firmographics_batch(db_session, [("Acme", "acme.com")]) == {}

    def test_domainless_skipped(self, db_session, monkeypatch):
        http = _Http({})
        self._enable_apollo(monkeypatch, http)
        out = cf.enrich_firmographics_batch(db_session, [("NoDomain Inc", "")], tenant_id=1)
        assert out == {}
        assert http.calls == []  # never looked up a domain-less company

    def test_resolves_by_domain_and_caps(self, db_session, monkeypatch):
        http = _Http({
            "a.com": _org(emp=30, industry="mfg"),
            "b.com": _org(emp=800, industry="logistics"),
            "c.com": _org(emp=10, industry="retail"),
        })
        self._enable_apollo(monkeypatch, http)
        items = [("A", "a.com"), ("B", "b.com"), ("C", "c.com")]
        out = cf.enrich_firmographics_batch(db_session, items, tenant_id=1, max_lookups=2)
        assert len(http.calls) == 2          # cap enforced
        assert out["a"]["company_size"] == "1-50"
        assert "c" not in out                # third skipped by cap


class TestResolverFirmographicWiring:
    """The sourcing resolver must fill company_size from the firmographic
    provider (which the LLM can't), and the free_only gate path must NEVER
    trigger the paid provider."""

    def test_resolver_fills_size_from_firmographic(self, db_session, monkeypatch):
        from app.services import company_enrichment as ce
        monkeypatch.setattr(cf, "get_firmographic_provider", lambda db, tenant_id=None: "apollo")
        monkeypatch.setattr(
            cf, "enrich_firmographics_batch",
            lambda db, items, tenant_id=None, max_lookups=100: {
                "acme": {"industry": "construction", "employee_count": 510, "company_size": "501-1000"}
            },
        )
        res = ce.resolve_company_metadata_batch(
            db_session, [("Acme", "acme.com")], tenant_id=1, use_llm=False,
        )
        assert res["acme"]["company_size"] == "501-1000"
        assert res["acme"]["employee_count"] == 510
        assert res["acme"]["industry"] == "construction"

    def test_free_only_never_calls_firmographic(self, db_session, monkeypatch):
        from app.services import company_enrichment as ce
        called = {"n": 0}
        monkeypatch.setattr(cf, "get_firmographic_provider", lambda db, tenant_id=None: "apollo")

        def _spy(*a, **k):
            called["n"] += 1
            return {}

        monkeypatch.setattr(cf, "enrich_firmographics_batch", _spy)
        res = ce.resolve_company_metadata_batch(
            db_session, [("Acme", "acme.com")], tenant_id=1, use_llm=False, free_only=True,
        )
        assert called["n"] == 0                       # paid provider never touched
        assert res["acme"]["company_size"] is None
