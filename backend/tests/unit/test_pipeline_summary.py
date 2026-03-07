"""Unit tests for pipeline summary scoring, builder functions, and fallback generation."""
import json
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

from app.services.pipeline_summary import (
    calculate_success_score,
    generate_pipeline_summary,
    _fallback_summary,
    _build_run_metadata,
    _build_source_breakdown,
    _build_api_diagnostics,
    ADAPTER_LABELS,
)
from app.db.models.job_run import JobRun, JobStatus

pytestmark = pytest.mark.unit


class TestCalculateSuccessScore:
    """Tests for the deterministic success score calculator."""

    def test_lead_sourcing_perfect_score(self):
        counters = {"inserted": 10, "updated": 2, "skipped": 0, "errors": 0}
        assert calculate_success_score("lead_sourcing", counters, "completed") == 100

    def test_lead_sourcing_with_errors(self):
        counters = {"inserted": 8, "updated": 2, "skipped": 0, "errors": 3}
        score = calculate_success_score("lead_sourcing", counters, "completed")
        # base = 10/13 * 100 = 76.9, penalty = 3*5 = 15, result = 62
        assert score == 62

    def test_lead_sourcing_zero_records(self):
        counters = {"inserted": 0, "updated": 0, "skipped": 0, "errors": 0}
        assert calculate_success_score("lead_sourcing", counters, "completed") == 0

    def test_lead_sourcing_error_penalty_capped(self):
        counters = {"inserted": 10, "updated": 0, "skipped": 0, "errors": 10}
        score = calculate_success_score("lead_sourcing", counters, "completed")
        # base = 10/20 * 100 = 50, penalty = min(50, 30) = 30, result = 20
        assert score == 20

    def test_contact_enrichment_perfect(self):
        counters = {"contacts_found": 15, "leads_enriched": 10, "skipped": 0, "errors": 0, "contacts_reused": 0}
        assert calculate_success_score("contact_enrichment", counters, "completed") == 100

    def test_contact_enrichment_cache_bonus(self):
        counters = {"contacts_found": 8, "leads_enriched": 10, "skipped": 2, "errors": 0, "contacts_reused": 5}
        score = calculate_success_score("contact_enrichment", counters, "completed")
        # base = 8/10 * 100 = 80, bonus = min(5*2, 10) = 10, result = 90
        assert score == 90

    def test_email_validation_all_valid(self):
        counters = {"validated": 20, "valid": 20, "invalid": 0, "errors": 0}
        assert calculate_success_score("email_validation", counters, "completed") == 100

    def test_email_validation_high_bounce(self):
        counters = {"validated": 20, "valid": 10, "invalid": 10, "errors": 0}
        score = calculate_success_score("email_validation", counters, "completed")
        # base = 10/20 * 100 = 50, bounce_rate = 0.5, penalty = min(200, 20) = 20, result = 30
        assert score == 30

    def test_outreach_all_sent(self):
        counters = {"sent": 25, "total": 25, "errors": 0}
        assert calculate_success_score("outreach_send", counters, "completed") == 100

    def test_outreach_with_errors(self):
        counters = {"sent": 20, "total": 25, "errors": 3}
        score = calculate_success_score("outreach_send", counters, "completed")
        # base = 20/25 * 100 = 80, penalty = min(30, 40) = 30, result = 50
        assert score == 50

    def test_outreach_mailmerge(self):
        counters = {"exported": 30, "total": 30}
        assert calculate_success_score("outreach_mailmerge", counters, "completed") == 100

    def test_failed_status_always_zero(self):
        counters = {"inserted": 10, "updated": 5, "skipped": 0, "errors": 0}
        assert calculate_success_score("lead_sourcing", counters, "failed") == 0

    def test_unknown_pipeline_returns_50(self):
        counters = {"some_metric": 100}
        assert calculate_success_score("custom_pipeline", counters, "completed") == 50

    def test_empty_counters(self):
        assert calculate_success_score("lead_sourcing", {}, "completed") == 0


class TestBuildRunMetadata:
    """Tests for _build_run_metadata."""

    def test_basic_metadata(self, db_session):
        run = JobRun(
            pipeline_name="lead_sourcing",
            status=JobStatus.COMPLETED,
            triggered_by="admin@test.com",
        )
        db_session.add(run)
        db_session.commit()
        db_session.refresh(run)

        meta = _build_run_metadata(run)
        assert meta["run_id"] == run.run_id
        assert meta["pipeline_name"] == "lead_sourcing"
        assert meta["pipeline_label"] == "Lead Sourcing"
        assert meta["status"] == "completed"
        assert meta["triggered_by"] == "admin@test.com"

    def test_duration_calculation(self, db_session):
        run = JobRun(
            pipeline_name="contact_enrichment",
            status=JobStatus.COMPLETED,
            triggered_by="test@test.com",
            started_at=datetime(2026, 1, 1, 10, 0, 0),
            ended_at=datetime(2026, 1, 1, 10, 5, 30),
        )
        db_session.add(run)
        db_session.commit()
        db_session.refresh(run)

        meta = _build_run_metadata(run)
        assert meta["duration_seconds"] == 330.0

    def test_no_timestamps(self, db_session):
        run = JobRun(
            pipeline_name="lead_sourcing",
            status=JobStatus.RUNNING,
            triggered_by="test@test.com",
        )
        db_session.add(run)
        db_session.commit()
        db_session.refresh(run)

        meta = _build_run_metadata(run)
        assert meta["duration_seconds"] is None


class TestBuildSourceBreakdown:
    """Tests for _build_source_breakdown."""

    def test_lead_sourcing_new_format(self):
        counters = {
            "per_source_detail": {
                "jsearch": {"fetched": 45, "new": 30, "existing_in_db": 10, "skipped_dedup": 5},
                "apollo": {"fetched": 20, "new": 15, "existing_in_db": 3, "skipped_dedup": 2},
            }
        }
        result = _build_source_breakdown("lead_sourcing", counters)
        assert len(result) == 2
        jsearch = next(r for r in result if r["source_name"] == "jsearch")
        assert jsearch["source_label"] == "JSearch (RapidAPI)"
        assert jsearch["total_retrieved"] == 45
        assert jsearch["new_records"] == 30
        assert jsearch["existing_in_db"] == 10
        assert jsearch["skipped"] == 5

    def test_lead_sourcing_legacy_format(self):
        counters = {
            "per_source": {"jsearch": 30, "apollo": 0},
        }
        result = _build_source_breakdown("lead_sourcing", counters)
        assert len(result) == 2
        jsearch = next(r for r in result if r["source_name"] == "jsearch")
        assert jsearch["total_retrieved"] == 30
        assert jsearch["status"] == "success"
        apollo = next(r for r in result if r["source_name"] == "apollo")
        assert apollo["total_retrieved"] == 0
        assert apollo["status"] == "warning"

    def test_lead_sourcing_empty_counters(self):
        result = _build_source_breakdown("lead_sourcing", {})
        assert result == []

    def test_contact_enrichment_with_adapter_stats(self):
        counters = {
            "adapter_stats": {
                "apollo": {"calls": 10, "contacts_returned": 25, "no_results": 2, "errors": 0},
            },
            "contacts_reused": 5,
        }
        result = _build_source_breakdown("contact_enrichment", counters)
        assert len(result) == 1
        assert result[0]["source_name"] == "apollo"
        assert result[0]["total_retrieved"] == 25
        assert result[0]["existing_in_db"] == 5

    def test_email_validation_breakdown(self):
        counters = {"provider_used": "neverbounce", "validated": 100, "valid": 85, "invalid": 10, "catch_all": 3, "unknown": 2, "errors": 0}
        result = _build_source_breakdown("email_validation", counters)
        assert len(result) == 1
        assert result[0]["source_name"] == "neverbounce"
        assert result[0]["total_retrieved"] == 100
        assert result[0]["new_records"] == 85

    def test_outreach_send_with_per_mailbox(self):
        counters = {
            "per_mailbox": {
                "sales@co.com": {"sent": 10, "errors": 0},
                "outreach@co.com": {"sent": 8, "errors": 1},
            }
        }
        result = _build_source_breakdown("outreach_send", counters)
        assert len(result) == 2
        sales = next(r for r in result if r["source_name"] == "sales@co.com")
        assert sales["new_records"] == 10
        assert sales["errors"] == 0

    def test_outreach_mailmerge_breakdown(self):
        counters = {"exported": 50, "skipped": 3}
        result = _build_source_breakdown("outreach_mailmerge", counters)
        assert len(result) == 1
        assert result[0]["source_name"] == "mailmerge"
        assert result[0]["total_retrieved"] == 50

    def test_api_diagnostics_overrides_status(self):
        """When api_diagnostics shows error, source_breakdown status is updated."""
        counters = {
            "per_source_detail": {
                "jsearch": {"fetched": 45, "new": 30, "existing_in_db": 10, "skipped_dedup": 5},
                "apollo": {"fetched": 0, "new": 0, "existing_in_db": 0, "skipped_dedup": 0},
            },
            "api_diagnostics": [
                {"adapter": "jsearch", "status": "success", "jobs_returned": 45, "error_type": None, "error_message": None},
                {"adapter": "apollo", "status": "error", "jobs_returned": 0, "error_type": "api_key_invalid", "error_message": "401 Unauthorized"},
            ],
        }
        result = _build_source_breakdown("lead_sourcing", counters)
        apollo = next(r for r in result if r["source_name"] == "apollo")
        assert apollo["status"] == "error"
        assert apollo["status_detail"] == "api_key_invalid"


class TestBuildApiDiagnostics:
    """Tests for _build_api_diagnostics."""

    def test_new_format_diagnostics(self):
        counters = {
            "api_diagnostics": [
                {"adapter": "jsearch", "status": "success", "jobs_returned": 45, "error_type": None, "error_message": None},
                {"adapter": "apollo", "status": "error", "jobs_returned": 0, "error_type": "api_key_invalid", "error_message": "401 Unauthorized"},
            ]
        }
        result = _build_api_diagnostics("lead_sourcing", counters)
        assert len(result) == 2
        assert result[0]["adapter_label"] == "JSearch (RapidAPI)"
        assert result[0]["status"] == "success"
        assert result[0]["records_returned"] == 45
        assert result[1]["status"] == "error"
        assert result[1]["status_detail"] == "api_key_invalid"

    def test_legacy_lead_sourcing_diagnostics(self):
        counters = {"sources": ["jsearch"], "per_source": {"jsearch": 30}, "errors": 0}
        result = _build_api_diagnostics("lead_sourcing", counters)
        assert len(result) == 1
        assert result[0]["adapter_name"] == "jsearch"
        assert result[0]["records_returned"] == 30

    def test_legacy_email_validation_diagnostics(self):
        counters = {"provider_used": "zerobounce", "validated": 50, "errors": 2}
        result = _build_api_diagnostics("email_validation", counters)
        assert len(result) == 1
        assert result[0]["adapter_name"] == "zerobounce"
        assert result[0]["status"] == "warning"

    def test_legacy_outreach_diagnostics(self):
        counters = {"sent": 20, "errors": 0}
        result = _build_api_diagnostics("outreach_send", counters)
        assert len(result) == 1
        assert result[0]["adapter_name"] == "smtp"
        assert result[0]["status"] == "success"

    def test_empty_counters_returns_empty(self):
        result = _build_api_diagnostics("lead_sourcing", {})
        assert result == []


class TestFallbackSummary:
    """Tests for the template-based fallback summary."""

    def test_fallback_completed(self):
        counters = {"inserted": 10, "updated": 2, "skipped": 1, "errors": 0}
        result = _fallback_summary("lead_sourcing", counters, 92, "completed", 45.0, None)
        assert "summary" in result
        assert "suggestions" in result
        assert "highlights" in result
        assert "completed" in result["summary"].lower()
        assert any("10" in h for h in result["highlights"])

    def test_fallback_failed(self):
        result = _fallback_summary("lead_sourcing", {}, 0, "failed", 5.0, "Connection timeout")
        assert "failed" in result["summary"].lower()
        assert "Connection timeout" in result["summary"]

    def test_fallback_cancelled(self):
        result = _fallback_summary("contact_enrichment", {}, 0, "cancelled", None, None)
        assert "cancelled" in result["summary"].lower()

    def test_fallback_high_error_rate_suggestion(self):
        counters = {"inserted": 5, "errors": 10}
        result = _fallback_summary("lead_sourcing", counters, 30, "completed", 10.0, None)
        assert any("error" in s.lower() for s in result["suggestions"])

    def test_fallback_perfect_score_suggestion(self):
        counters = {"inserted": 10, "updated": 0, "skipped": 0, "errors": 0}
        result = _fallback_summary("lead_sourcing", counters, 100, "completed", 10.0, None)
        assert any("perfect" in s.lower() or "no improvements" in s.lower() for s in result["suggestions"])

    def test_fallback_returns_valid_dict(self):
        result = _fallback_summary("email_validation", {"valid": 5, "invalid": 2}, 70, "completed", None, None)
        assert isinstance(result["summary"], str)
        assert isinstance(result["suggestions"], list)
        assert isinstance(result["highlights"], list)


class TestGeneratePipelineSummary:
    """Tests for the full summary generation with AI fallback."""

    def test_fallback_summary_no_ai(self, db_session):
        """When no AI adapter is configured, returns valid fallback dict with enhanced fields."""
        run = JobRun(
            pipeline_name="lead_sourcing",
            status=JobStatus.COMPLETED,
            counters_json='{"inserted": 10, "updated": 2, "skipped": 1, "errors": 0}',
            triggered_by="test@test.com",
        )
        db_session.add(run)
        db_session.commit()
        db_session.refresh(run)

        with patch("app.services.warmup.content_generator.get_ai_adapter", return_value=None):
            result = generate_pipeline_summary(db_session, run)

        assert result["success_score"] == 92  # (10+2)/(10+2+1+0) * 100 = 92.3 -> rounds to 92
        assert result["ai_generated"] is False
        assert "summary" in result
        assert "suggestions" in result
        assert "highlights" in result
        assert "generated_at" in result
        # Enhanced fields
        assert "run_metadata" in result
        assert "source_breakdown" in result
        assert "api_diagnostics" in result
        assert "counters" in result
        assert result["run_metadata"]["pipeline_name"] == "lead_sourcing"
        assert result["run_metadata"]["pipeline_label"] == "Lead Sourcing"

    def test_summary_with_ai_adapter(self, db_session):
        """When AI adapter is available, uses it for narrative."""
        run = JobRun(
            pipeline_name="contact_enrichment",
            status=JobStatus.COMPLETED,
            counters_json='{"contacts_found": 8, "skipped": 2, "errors": 0}',
            triggered_by="test@test.com",
        )
        db_session.add(run)
        db_session.commit()
        db_session.refresh(run)

        mock_adapter = MagicMock()
        mock_adapter._call_api.return_value = json.dumps({
            "summary": "AI generated summary text.",
            "suggestions": ["Try adding more sources"],
            "highlights": ["8 contacts discovered"],
        })

        with patch("app.services.warmup.content_generator.get_ai_adapter", return_value=mock_adapter):
            result = generate_pipeline_summary(db_session, run)

        assert result["ai_generated"] is True
        assert result["summary"] == "AI generated summary text."
        assert len(result["suggestions"]) == 1
        assert "source_breakdown" in result
        assert "api_diagnostics" in result
        mock_adapter._call_api.assert_called_once()

    def test_ai_failure_falls_back(self, db_session):
        """When AI adapter throws, falls back to template."""
        run = JobRun(
            pipeline_name="lead_sourcing",
            status=JobStatus.COMPLETED,
            counters_json='{"inserted": 5, "updated": 0, "skipped": 0, "errors": 0}',
            triggered_by="test@test.com",
        )
        db_session.add(run)
        db_session.commit()
        db_session.refresh(run)

        mock_adapter = MagicMock()
        mock_adapter._call_api.side_effect = RuntimeError("API timeout")

        with patch("app.services.warmup.content_generator.get_ai_adapter", return_value=mock_adapter):
            result = generate_pipeline_summary(db_session, run)

        assert result["ai_generated"] is False
        assert result["success_score"] == 100
        assert isinstance(result["summary"], str)
        assert isinstance(result["source_breakdown"], list)
        assert isinstance(result["api_diagnostics"], list)

    def test_failed_run_score_zero(self, db_session):
        """Failed runs always get score 0."""
        run = JobRun(
            pipeline_name="outreach",
            status=JobStatus.FAILED,
            counters_json='{"sent": 5, "total": 10, "errors": 5}',
            error_message="SMTP connection failed",
            triggered_by="test@test.com",
        )
        db_session.add(run)
        db_session.commit()
        db_session.refresh(run)

        with patch("app.services.warmup.content_generator.get_ai_adapter", return_value=None):
            result = generate_pipeline_summary(db_session, run)

        assert result["success_score"] == 0
        assert "run_metadata" in result

    def test_enriched_counters_produce_source_breakdown(self, db_session):
        """Enriched lead_sourcing counters produce detailed source breakdown."""
        counters = json.dumps({
            "inserted": 25, "updated": 0, "skipped": 5, "errors": 1,
            "sources": ["jsearch", "apollo"],
            "per_source": {"jsearch": 30, "apollo": 0},
            "per_source_detail": {
                "jsearch": {"fetched": 30, "new": 25, "existing_in_db": 0, "skipped_dedup": 5},
                "apollo": {"fetched": 0, "new": 0, "existing_in_db": 0, "skipped_dedup": 0},
            },
            "api_diagnostics": [
                {"adapter": "jsearch", "status": "success", "jobs_returned": 30, "error_type": None, "error_message": None},
                {"adapter": "apollo", "status": "error", "jobs_returned": 0, "error_type": "api_key_invalid", "error_message": "401 Unauthorized"},
            ],
        })
        run = JobRun(
            pipeline_name="lead_sourcing",
            status=JobStatus.COMPLETED,
            counters_json=counters,
            triggered_by="test@test.com",
        )
        db_session.add(run)
        db_session.commit()
        db_session.refresh(run)

        with patch("app.services.warmup.content_generator.get_ai_adapter", return_value=None):
            result = generate_pipeline_summary(db_session, run)

        assert len(result["source_breakdown"]) == 2
        jsearch = next(s for s in result["source_breakdown"] if s["source_name"] == "jsearch")
        assert jsearch["new_records"] == 25
        assert jsearch["status"] == "success"

        apollo = next(s for s in result["source_breakdown"] if s["source_name"] == "apollo")
        assert apollo["status"] == "error"
        assert apollo["status_detail"] == "api_key_invalid"

        assert len(result["api_diagnostics"]) == 2
        apollo_diag = next(d for d in result["api_diagnostics"] if d["adapter_name"] == "apollo")
        assert apollo_diag["error_message"] == "401 Unauthorized"
