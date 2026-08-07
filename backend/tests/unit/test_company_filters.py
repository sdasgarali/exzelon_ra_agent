"""Unit tests for company-level exclusion filters (size / industry / placeholder)."""
import pytest

from app.services.company_filters import (
    parse_employee_count,
    exceeds_size_ceiling,
    exceeds_size_ceiling_any,
    below_size_floor,
    below_size_floor_any,
    size_buckets_within_ceiling,
    industry_is_excluded,
    is_placeholder_company,
    salary_below_threshold,
)

pytestmark = pytest.mark.unit


class TestExceedsSizeCeilingAny:
    """Conservative multi-signal ceiling — drop when the LARGEST signal is over."""

    def test_understated_headcount_with_large_band_is_dropped(self):
        # The R1603 bug: tagged-member headcount 156, self-reported band 1001-5000.
        assert exceeds_size_ceiling_any([156, "1001-5000"], 200) is True

    def test_understated_headcount_alone_is_kept(self):
        assert exceeds_size_ceiling_any([156], 200) is False

    def test_band_order_independent(self):
        assert exceeds_size_ceiling_any(["1001-5000", 156], 200) is True

    def test_all_signals_within_ceiling_kept(self):
        assert exceeds_size_ceiling_any([50, "51-200"], 200) is False

    @pytest.mark.parametrize("values", [[], [None], [None, ""], ["unknown", None]])
    def test_all_unknown_never_dropped(self, values):
        assert exceeds_size_ceiling_any(values, 200) is False

    def test_zero_ceiling_disables(self):
        assert exceeds_size_ceiling_any([9999, "10001+"], 0) is False


class TestBelowSizeFloorAny:
    def test_dropped_only_when_largest_below_floor(self):
        assert below_size_floor_any([5, "1-10"], 50) is True

    def test_kept_when_any_signal_meets_floor(self):
        assert below_size_floor_any([5, "201-500"], 50) is False

    def test_all_unknown_never_dropped(self):
        assert below_size_floor_any([None, ""], 50) is False

    def test_zero_floor_disables(self):
        assert below_size_floor_any([1], 0) is False


class TestSizeBucketsWithinCeiling:
    def test_ceiling_200_excludes_201_and_up(self):
        assert size_buckets_within_ceiling(200) == ["1", "2-10", "11-50", "51-200"]

    def test_ceiling_500_includes_201_500(self):
        assert size_buckets_within_ceiling(500) == [
            "1", "2-10", "11-50", "51-200", "201-500",
        ]

    @pytest.mark.parametrize("ceiling", [0, -1])
    def test_non_positive_ceiling_off(self, ceiling):
        assert size_buckets_within_ceiling(ceiling) == []


class TestSalaryBelowThreshold:
    @pytest.mark.parametrize("smin,smax,thr,expected", [
        (None, None, 40000, False),      # unknown → keep
        (25000, 32000, 40000, True),     # best case below floor → drop
        (25000, 55000, 40000, False),    # range spans floor → keep
        (None, 38000, 40000, True),      # only known figure below → drop
        (45000, None, 40000, False),     # known above → keep
        (30, 45, 40000, False),          # hourly-looking → keep (guard)
        (32000, 32000, 0, False),        # threshold disabled → keep
        (32000, 32000, None, False),     # no threshold → keep
        ("30000", "35000", 40000, True), # string figures parsed
    ])
    def test_salary(self, smin, smax, thr, expected):
        assert salary_below_threshold(smin, smax, thr) is expected


class TestParseEmployeeCount:
    @pytest.mark.parametrize("value,expected", [
        (250, 250),
        (250.0, 250),
        ("250", 250),
        ("201-500", 201),        # range → lower bound
        ("501-1000", 501),
        ("5000+", 5000),
        ("10K+ employees", 10000),
        ("1K-5K employees", 1000),
        ("501-1K employees", 501),
        ("5K-10K employees", 5000),
        ("1,250", 1250),
        ("", None),
        (None, None),
        ("unknown", None),
        (0, None),
        (True, None),           # bool guard
    ])
    def test_parse(self, value, expected):
        assert parse_employee_count(value) == expected


class TestExceedsSizeCeiling:
    def test_over_ceiling_dropped(self):
        assert exceeds_size_ceiling("1K-5K employees", 500) is True
        assert exceeds_size_ceiling("501-1K employees", 500) is True
        assert exceeds_size_ceiling("10K+ employees", 500) is True
        assert exceeds_size_ceiling(750, 500) is True

    def test_within_ceiling_kept(self):
        assert exceeds_size_ceiling("201-500", 500) is False
        assert exceeds_size_ceiling("51-200", 500) is False
        assert exceeds_size_ceiling(500, 500) is False

    def test_unknown_size_never_dropped(self):
        assert exceeds_size_ceiling(None, 500) is False
        assert exceeds_size_ceiling("", 500) is False
        assert exceeds_size_ceiling("unknown", 500) is False

    def test_disabled_ceiling(self):
        assert exceeds_size_ceiling(99999, 0) is False


class TestBelowSizeFloor:
    def test_under_floor_dropped(self):
        assert below_size_floor("2-10 employees", 50) is True
        assert below_size_floor("11-50 employees", 100) is True
        assert below_size_floor(10, 50) is True

    def test_at_or_above_floor_kept(self):
        assert below_size_floor("51-200", 50) is False   # lower bound 51 >= 50
        assert below_size_floor(50, 50) is False          # equal → keep
        assert below_size_floor("201-500", 50) is False

    def test_unknown_size_never_dropped(self):
        assert below_size_floor(None, 50) is False
        assert below_size_floor("", 50) is False
        assert below_size_floor("unknown", 50) is False

    def test_floor_of_one_is_noop(self):
        # Default floor=1 keeps every company with a parseable size.
        assert below_size_floor("2-10 employees", 1) is False
        assert below_size_floor(1, 1) is False
        assert below_size_floor(500, 1) is False

    def test_disabled_floor(self):
        assert below_size_floor(1, 0) is False
        assert below_size_floor(1, -5) is False


class TestIndustryIsExcluded:
    @pytest.mark.parametrize("industry", [
        "Computer Software",
        "Information Technology & Services",
        "IT Services and IT Consulting",
        "Software Development",
        "Staffing and Recruiting",
        "Staffing & Recruiting",
        "Government Administration",
        "Public Administration",
        # Insurance excluded per ICP decision 2026-07-17.
        "Insurance",
        "Insurance Carriers",
        "Insurance Agencies and Brokerages",
    ])
    def test_excluded(self, industry):
        assert industry_is_excluded(industry) is True

    @pytest.mark.parametrize("industry", [
        "Financial Services",
        "Healthcare",
        "Manufacturing",
        "Construction",
        "Biotechnology",     # must NOT match on bare "technology"
        "Retail",
        "",
        None,
    ])
    def test_not_excluded(self, industry):
        assert industry_is_excluded(industry) is False

    def test_custom_keywords(self):
        assert industry_is_excluded("Language Schools", ["language schools"]) is True
        assert industry_is_excluded("Insurance", ["language schools"]) is False


class TestIsPlaceholderCompany:
    @pytest.mark.parametrize("name", [
        "Confidential", "confidential", "  Confidential  ",
        "Unknown Company", "unknown", "N/A", "Undisclosed",
        "Private Company", "", "   ", None,
    ])
    def test_placeholder(self, name):
        assert is_placeholder_company(name) is True

    @pytest.mark.parametrize("name", [
        "Acme Foods", "The Hanover Insurance Group", "Suffolk Construction",
    ])
    def test_real_company(self, name):
        assert is_placeholder_company(name) is False
