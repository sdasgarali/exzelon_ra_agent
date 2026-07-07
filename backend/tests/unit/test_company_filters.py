"""Unit tests for company-level exclusion filters (size / industry / placeholder)."""
import pytest

from app.services.company_filters import (
    parse_employee_count,
    exceeds_size_ceiling,
    industry_is_excluded,
    is_placeholder_company,
    salary_below_threshold,
)

pytestmark = pytest.mark.unit


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
    ])
    def test_excluded(self, industry):
        assert industry_is_excluded(industry) is True

    @pytest.mark.parametrize("industry", [
        "Insurance",
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
