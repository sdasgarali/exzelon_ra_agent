"""Unit tests for applicant-count parsing + threshold (no network)."""
import pytest

from app.services.applicant_parser import parse_applicant_count, applicant_count_exceeds

pytestmark = pytest.mark.unit


class TestParseApplicantCount:
    @pytest.mark.parametrize("text,expected", [
        ("Over 100 applicants", 101),
        ("100+ applicants", 101),
        ("Over 100 people clicked apply", 101),
        ("47 people clicked apply", 47),
        ("47 clicked apply", 47),
        ("Be among the first 25 applicants", 25),
        ("1,024 applicants", 1024),
        ("38 applicants", 38),
        ("12 applies", 12),
        # Strongest signal wins when several appear.
        ("Be among the first 25 applicants ... Over 200 applicants", 201),
        # Not an applicant count.
        ("2K alumni", None),
        ("Posted 3 days ago", None),
        ("", None),
        (None, None),
    ])
    def test_parse(self, text, expected):
        assert parse_applicant_count(text) == expected


class TestApplicantCountExceeds:
    def test_over_threshold_dropped(self):
        assert applicant_count_exceeds(150, 100) is True
        assert applicant_count_exceeds(101, 100) is True

    def test_at_or_below_kept(self):
        assert applicant_count_exceeds(100, 100) is False   # equal → keep
        assert applicant_count_exceeds(20, 100) is False

    def test_unknown_never_dropped(self):
        assert applicant_count_exceeds(None, 100) is False

    def test_disabled_threshold(self):
        assert applicant_count_exceeds(9999, 0) is False
        assert applicant_count_exceeds(9999, -1) is False
