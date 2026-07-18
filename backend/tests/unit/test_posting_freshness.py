"""Unit tests for job-posting freshness filters (stale age + expiration)."""
from datetime import date, datetime, timedelta

import pytest

from app.services.posting_freshness import (
    coerce_date,
    posting_too_old,
    posting_expired,
)

pytestmark = pytest.mark.unit

TODAY = date(2026, 7, 18)


class TestCoerceDate:
    @pytest.mark.parametrize("value,expected", [
        (date(2026, 7, 1), date(2026, 7, 1)),
        (datetime(2026, 7, 1, 9, 30), date(2026, 7, 1)),
        ("2026-07-01", date(2026, 7, 1)),
        ("2026-07-01T09:30:00Z", date(2026, 7, 1)),
        ("2026-07-01 09:30:00", date(2026, 7, 1)),
        ("", None),
        (None, None),
        ("n/a", None),
        ("not-a-date", None),
        (123, None),
        (True, None),          # bool guard
    ])
    def test_coerce(self, value, expected):
        assert coerce_date(value) == expected


class TestPostingTooOld:
    def test_old_posting_dropped(self):
        assert posting_too_old(TODAY - timedelta(days=30), 14, today=TODAY) is True
        assert posting_too_old("2026-06-01", 14, today=TODAY) is True   # ~47d

    def test_within_window_kept(self):
        assert posting_too_old(TODAY - timedelta(days=14), 14, today=TODAY) is False  # boundary
        assert posting_too_old(TODAY - timedelta(days=3), 14, today=TODAY) is False
        assert posting_too_old(TODAY, 14, today=TODAY) is False

    def test_future_posting_kept(self):
        assert posting_too_old(TODAY + timedelta(days=5), 14, today=TODAY) is False

    def test_unknown_date_never_dropped(self):
        assert posting_too_old(None, 14, today=TODAY) is False
        assert posting_too_old("", 14, today=TODAY) is False
        assert posting_too_old("unknown", 14, today=TODAY) is False

    def test_disabled_gate(self):
        assert posting_too_old(TODAY - timedelta(days=999), 0, today=TODAY) is False
        assert posting_too_old(TODAY - timedelta(days=999), -1, today=TODAY) is False


class TestPostingExpired:
    def test_past_expiration_dropped(self):
        assert posting_expired(TODAY - timedelta(days=1), today=TODAY) is True
        assert posting_expired("2026-07-01", today=TODAY) is True

    def test_future_or_today_expiration_kept(self):
        assert posting_expired(TODAY, today=TODAY) is False          # expires today → still open
        assert posting_expired(TODAY + timedelta(days=1), today=TODAY) is False

    def test_unknown_expiration_never_dropped(self):
        assert posting_expired(None, today=TODAY) is False
        assert posting_expired("", today=TODAY) is False


class TestFreshnessGateHelper:
    """The pipeline-level _apply_freshness_gate over plain job dicts."""

    def _run(self, jobs, **kw):
        from app.services.pipelines import lead_sourcing as ls
        counters = {}
        kept = ls._apply_freshness_gate(jobs, counters, **kw)
        return kept, counters

    def test_drops_stale_and_expired_keeps_fresh_and_unknown(self):
        old = (date.today() - timedelta(days=40)).isoformat()
        recent = (date.today() - timedelta(days=2)).isoformat()
        past_exp = (date.today() - timedelta(days=1)).isoformat()
        jobs = [
            {"job_title": "fresh", "posting_date": recent},
            {"job_title": "stale", "posting_date": old},
            {"job_title": "expired", "posting_date": recent, "expiration_date": past_exp},
            {"job_title": "unknown-date"},  # no dates → kept
        ]
        kept, counters = self._run(jobs, max_posting_age_days=14, drop_expired=True)
        titles = {j["job_title"] for j in kept}
        assert titles == {"fresh", "unknown-date"}
        assert counters["excluded_stale"] == 1
        assert counters["excluded_expired"] == 1

    def test_disabled_gate_keeps_everything(self):
        old = (date.today() - timedelta(days=400)).isoformat()
        jobs = [{"job_title": "ancient", "posting_date": old}]
        kept, counters = self._run(jobs, max_posting_age_days=0, drop_expired=False)
        assert len(kept) == 1
        assert counters["excluded_stale"] == 0
        assert counters["excluded_expired"] == 0

    def test_expired_respected_only_when_flag_on(self):
        past_exp = (date.today() - timedelta(days=5)).isoformat()
        recent = (date.today() - timedelta(days=1)).isoformat()
        jobs = [{"job_title": "exp", "posting_date": recent, "expiration_date": past_exp}]
        kept, _ = self._run(jobs, max_posting_age_days=14, drop_expired=False)
        assert len(kept) == 1  # expiration ignored when flag off
