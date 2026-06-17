"""Unit tests for job-source optimization: overlap groups + coverage tiers.

These guard the cost-saving routing: providers that share an index (SerpAPI &
SearchAPI = Google Jobs) never run together, and expensive/overlapping sources
are tiered below free/cheap/unique ones.
"""
import pytest

from app.services.pipelines import lead_sourcing as ls

pytestmark = pytest.mark.unit


def _names(pairs):
    return [n for n, _ in pairs]


class TestOverlapGroups:
    def test_searchapi_is_preferred_google_jobs_provider(self):
        # Decision: SearchAPI is primary; SerpAPI is the disabled fallback.
        assert ls.SOURCE_OVERLAP_GROUPS["google_jobs"][0] == "searchapi"
        assert "serpapi" in ls.SOURCE_OVERLAP_GROUPS["google_jobs"]

    def test_drops_serpapi_when_searchapi_present(self):
        adapters = [("searchapi", object()), ("serpapi", object()),
                    ("jsearch", object()), ("usajobs", object())]
        kept, skipped = ls._filter_overlap_groups(adapters, ls.SOURCE_OVERLAP_GROUPS)
        assert skipped == ["serpapi"]
        assert "serpapi" not in _names(kept)
        assert "searchapi" in _names(kept)
        # non-group providers are untouched
        assert "jsearch" in _names(kept) and "usajobs" in _names(kept)

    def test_keeps_serpapi_as_fallback_when_searchapi_absent(self):
        adapters = [("serpapi", object()), ("jsearch", object())]
        kept, skipped = ls._filter_overlap_groups(adapters, ls.SOURCE_OVERLAP_GROUPS)
        assert skipped == []
        assert "serpapi" in _names(kept)

    def test_no_group_members_present_is_noop(self):
        adapters = [("jsearch", object()), ("adzuna", object())]
        kept, skipped = ls._filter_overlap_groups(adapters, ls.SOURCE_OVERLAP_GROUPS)
        assert skipped == []
        assert _names(kept) == ["jsearch", "adzuna"]


class TestTierPartition:
    def test_free_cheap_unique_sources_are_tier1(self):
        adapters = [("usajobs", object()), ("jooble", object()), ("jsearch", object()),
                    ("adzuna", object()), ("theirstack", object())]
        tier1, tier2 = ls._partition_tiers(adapters, ls.SOURCE_TIERS)
        assert set(_names(tier1)) == {"usajobs", "jooble", "jsearch", "adzuna", "theirstack"}
        assert tier2 == []

    def test_expensive_sources_are_tier2_cheapest_first(self):
        adapters = [("coresignal", object()), ("searchapi", object()),
                    ("jobdatafeeds", object()), ("jsearch", object())]
        tier1, tier2 = ls._partition_tiers(adapters, ls.SOURCE_TIERS)
        assert _names(tier1) == ["jsearch"]
        # cheapest-first ordering by SOURCE_COST_RANK: searchapi(5) < jobdatafeeds(8) < coresignal(9)
        assert _names(tier2) == ["searchapi", "jobdatafeeds", "coresignal"]

    def test_unknown_source_defaults_to_tier1(self):
        adapters = [("some_new_source", object())]
        tier1, tier2 = ls._partition_tiers(adapters, ls.SOURCE_TIERS)
        assert _names(tier1) == ["some_new_source"]
        assert tier2 == []

    def test_custom_tier_map_override(self):
        # Operator can demote jsearch to tier 2 via settings override.
        adapters = [("jsearch", object()), ("usajobs", object())]
        tier1, tier2 = ls._partition_tiers(adapters, {"jsearch": 2, "usajobs": 1})
        assert _names(tier1) == ["usajobs"]
        assert _names(tier2) == ["jsearch"]
