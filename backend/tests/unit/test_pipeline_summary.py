"""Unit tests for pipeline summary scoring, builder functions, and fallback generation."""
import json
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

from app.services.pipeline_summary import (
    calculate_success_score,
    build_quality_funnel,
    build_error_details,
    _fill_error_analysis_fallback,
    generate_pipeline_summary,
    _fallback_summary,
    _build_run_metadata,
    _build_source_breakdown,
    _build_api_diagnostics,
    ADAPTER_LABELS,
    ERROR_TYPE_FALLBACK_SOLUTIONS,
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


class TestBuildQualityFunnel:
    """Tests for the quality funnel builder."""

    def test_lead_sourcing_funnel(self):
        counters = {"inserted": 285, "updated": 103, "skipped": 812, "errors": 2}
        result = build_quality_funnel("lead_sourcing", counters, "completed")
        assert result["total_discovered"] == 285 + 103 + 812 + 2
        assert result["new_added"] == 285
        assert result["updated"] == 103
        assert result["duplicates_caught"] == 812
        assert result["errors"] == 2
        labels = [fb["label"] for fb in result["filter_breakdown"]]
        assert "Duplicates removed" in labels
        assert "Records updated" in labels
        assert "Errors" in labels

    def test_contact_enrichment_funnel(self):
        counters = {"contacts_found": 50, "contacts_reused": 10, "skipped": 3, "errors": 1}
        result = build_quality_funnel("contact_enrichment", counters, "completed")
        assert result["new_added"] == 50
        assert result["updated"] == 10
        assert result["duplicates_caught"] == 3
        assert result["errors"] == 1
        labels = [fb["label"] for fb in result["filter_breakdown"]]
        assert "Reused from cache" in labels

    def test_email_validation_funnel(self):
        counters = {"validated": 100, "valid": 80, "invalid": 10, "catch_all": 5, "unknown": 3, "errors": 2}
        result = build_quality_funnel("email_validation", counters, "completed")
        assert result["new_added"] == 80
        assert result["duplicates_caught"] == 10 + 5 + 3
        assert result["errors"] == 2
        labels = [fb["label"] for fb in result["filter_breakdown"]]
        assert "Invalid emails" in labels
        assert "Catch-all domains" in labels
        assert "Unknown status" in labels
        assert "Errors" in labels

    def test_outreach_funnel(self):
        counters = {"sent": 25, "skipped": 5, "total": 33, "errors": 3}
        result = build_quality_funnel("outreach_send", counters, "completed")
        assert result["new_added"] == 25
        assert result["duplicates_caught"] == 5
        assert result["total_discovered"] == 33
        assert result["errors"] == 3

    def test_outreach_alias(self):
        counters = {"sent": 10, "total": 10, "errors": 0}
        result = build_quality_funnel("outreach", counters, "completed")
        assert result["new_added"] == 10

    def test_failed_status_all_zeros(self):
        counters = {"inserted": 100, "updated": 50, "skipped": 30, "errors": 0}
        result = build_quality_funnel("lead_sourcing", counters, "failed")
        assert result["new_added"] == 0
        assert result["updated"] == 0
        assert result["duplicates_caught"] == 0
        assert result["errors"] >= 1
        assert len(result["filter_breakdown"]) == 1
        assert result["filter_breakdown"][0]["label"] == "Errors"

    def test_zero_records_empty_funnel(self):
        counters = {"inserted": 0, "updated": 0, "skipped": 0, "errors": 0}
        result = build_quality_funnel("lead_sourcing", counters, "completed")
        assert result["total_discovered"] == 0
        assert result["new_added"] == 0
        assert result["filter_breakdown"] == []

    def test_unknown_pipeline_empty(self):
        result = build_quality_funnel("custom_pipeline", {"foo": 42}, "completed")
        assert result["total_discovered"] == 0
        assert result["new_added"] == 0
        assert result["filter_breakdown"] == []

    def test_mailmerge_funnel(self):
        counters = {"exported": 30, "skipped": 2, "total": 32}
        result = build_quality_funnel("outreach_mailmerge", counters, "completed")
        assert result["new_added"] == 30
        assert result["duplicates_caught"] == 2
        assert result["total_discovered"] == 32


class TestBuildRunMetadata:
    """Tests for _build_run_metadata."""

    def test_basic_metadata(self, db_session, test_tenant):
        run = JobRun(
            tenant_id=test_tenant.tenant_id,
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

    def test_duration_calculation(self, db_session, test_tenant):
        run = JobRun(
            tenant_id=test_tenant.tenant_id,
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

    def test_no_timestamps(self, db_session, test_tenant):
        run = JobRun(
            tenant_id=test_tenant.tenant_id,
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


class TestBuildErrorDetails:
    """Tests for build_error_details extraction from counters and error_message."""

    def test_extracts_errors_from_api_diagnostics(self):
        counters = {
            "api_diagnostics": [
                {"adapter": "apollo", "status": "error", "error_type": "api_key_invalid", "error_message": "401 Unauthorized"},
            ]
        }
        result = build_error_details(counters)
        assert len(result) == 1
        assert result[0]["error_type"] == "api_key_invalid"
        assert result[0]["adapter"] == "apollo"
        assert result[0]["adapter_label"] == "Apollo.io"
        assert result[0]["message"] == "401 Unauthorized"
        assert result[0]["root_cause"] == ""
        assert result[0]["proposed_solutions"] == []

    def test_extracts_top_level_error_message(self):
        counters = {}
        result = build_error_details(counters, "Connection timeout")
        assert len(result) == 1
        assert result[0]["error_type"] == "pipeline_failure"
        assert result[0]["adapter"] is None
        assert result[0]["adapter_label"] == "Pipeline"
        assert result[0]["message"] == "Connection timeout"

    def test_deduplicates_error_message_matching_diagnostics(self):
        counters = {
            "api_diagnostics": [
                {"adapter": "apollo", "status": "error", "error_type": "api_key_invalid", "error_message": "401 Unauthorized"},
            ]
        }
        result = build_error_details(counters, "401 Unauthorized")
        assert len(result) == 1  # Not duplicated

    def test_empty_when_no_errors(self):
        counters = {
            "api_diagnostics": [
                {"adapter": "jsearch", "status": "success", "error_type": None, "error_message": None},
            ]
        }
        result = build_error_details(counters)
        assert result == []

    def test_multiple_adapter_errors(self):
        counters = {
            "api_diagnostics": [
                {"adapter": "apollo", "status": "error", "error_type": "api_key_invalid", "error_message": "401"},
                {"adapter": "jsearch", "status": "error", "error_type": "rate_limited", "error_message": "429 Too Many"},
            ]
        }
        result = build_error_details(counters)
        assert len(result) == 2
        assert result[0]["error_type"] == "api_key_invalid"
        assert result[1]["error_type"] == "rate_limited"

    def test_warning_with_error_type_included(self):
        counters = {
            "api_diagnostics": [
                {"adapter": "neverbounce", "status": "warning", "error_type": "high_error_rate", "error_message": "50% errors"},
            ]
        }
        result = build_error_details(counters)
        assert len(result) == 1
        assert result[0]["error_type"] == "high_error_rate"

    def test_warning_without_error_type_excluded(self):
        counters = {
            "api_diagnostics": [
                {"adapter": "jsearch", "status": "warning", "error_type": None, "error_message": None},
            ]
        }
        result = build_error_details(counters)
        assert result == []

    def test_missing_api_diagnostics_key(self):
        counters = {"inserted": 10}
        result = build_error_details(counters)
        assert result == []


class TestFillErrorAnalysisFallback:
    """Tests for _fill_error_analysis_fallback template filling."""

    def test_fills_known_error_type_with_substitution(self):
        errors = [{
            "error_type": "api_key_invalid",
            "adapter": "apollo",
            "adapter_label": "Apollo.io",
            "message": "401",
            "root_cause": "",
            "proposed_solutions": [],
        }]
        _fill_error_analysis_fallback(errors)
        assert "Apollo.io" in errors[0]["root_cause"]
        assert len(errors[0]["proposed_solutions"]) >= 2
        assert any("Apollo.io" in s for s in errors[0]["proposed_solutions"])

    def test_falls_back_to_unknown_for_unrecognized_type(self):
        errors = [{
            "error_type": "totally_new_error_type",
            "adapter": "x",
            "adapter_label": "X Service",
            "message": "boom",
            "root_cause": "",
            "proposed_solutions": [],
        }]
        _fill_error_analysis_fallback(errors)
        assert "X Service" in errors[0]["root_cause"]
        assert len(errors[0]["proposed_solutions"]) >= 1


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

    def test_fallback_clean_run_suggestion(self):
        counters = {"inserted": 10, "updated": 0, "skipped": 0, "errors": 0}
        result = _fallback_summary("lead_sourcing", counters, 100, "completed", 10.0, None)
        assert any("clean run" in s.lower() for s in result["suggestions"])

    def test_fallback_returns_valid_dict(self):
        result = _fallback_summary("email_validation", {"valid": 5, "invalid": 2}, 70, "completed", None, None)
        assert isinstance(result["summary"], str)
        assert isinstance(result["suggestions"], list)
        assert isinstance(result["highlights"], list)

    def test_fallback_includes_error_analysis_when_errors_exist(self):
        error_details = [{
            "error_type": "api_key_invalid",
            "adapter": "apollo",
            "adapter_label": "Apollo.io",
            "message": "401",
            "root_cause": "",
            "proposed_solutions": [],
        }]
        result = _fallback_summary("lead_sourcing", {"inserted": 5, "errors": 1}, 60, "completed", 10.0, None, error_details)
        assert "error_analysis" in result
        assert len(result["error_analysis"]) == 1
        assert result["error_analysis"][0]["root_cause"] != ""
        assert len(result["error_analysis"][0]["proposed_solutions"]) >= 1

    def test_fallback_empty_error_analysis_when_clean(self):
        result = _fallback_summary("lead_sourcing", {"inserted": 10, "errors": 0}, 100, "completed", 10.0, None)
        assert result["error_analysis"] == []


class TestGeneratePipelineSummary:
    """Tests for the full summary generation with AI fallback."""

    def test_fallback_summary_no_ai(self, db_session, test_tenant):
        """When no AI adapter is configured, returns valid fallback dict with enhanced fields."""
        run = JobRun(
            tenant_id=test_tenant.tenant_id,
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
        # Quality funnel
        assert "quality_funnel" in result
        qf = result["quality_funnel"]
        assert qf["new_added"] == 10
        assert qf["updated"] == 2

    def test_summary_with_ai_adapter(self, db_session, test_tenant):
        """When AI adapter is available, uses it for narrative."""
        run = JobRun(
            tenant_id=test_tenant.tenant_id,
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

    def test_ai_failure_falls_back(self, db_session, test_tenant):
        """When AI adapter throws, falls back to template."""
        run = JobRun(
            tenant_id=test_tenant.tenant_id,
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

    def test_failed_run_score_zero(self, db_session, test_tenant):
        """Failed runs always get score 0."""
        run = JobRun(
            tenant_id=test_tenant.tenant_id,
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

    def test_enriched_counters_produce_source_breakdown(self, db_session, test_tenant):
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
            tenant_id=test_tenant.tenant_id,
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

    def test_error_analysis_populated_from_diagnostics(self, db_session, test_tenant):
        """api_diagnostics with errors produces error_analysis with root_cause + solutions."""
        counters = json.dumps({
            "inserted": 25, "updated": 0, "skipped": 5, "errors": 1,
            "api_diagnostics": [
                {"adapter": "jsearch", "status": "success", "jobs_returned": 30, "error_type": None, "error_message": None},
                {"adapter": "apollo", "status": "error", "jobs_returned": 0, "error_type": "api_key_invalid", "error_message": "401 Unauthorized"},
            ],
        })
        run = JobRun(
            tenant_id=test_tenant.tenant_id,
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

        assert "error_analysis" in result
        assert len(result["error_analysis"]) == 1
        ea = result["error_analysis"][0]
        assert ea["error_type"] == "api_key_invalid"
        assert ea["adapter"] == "apollo"
        assert ea["adapter_label"] == "Apollo.io"
        assert ea["root_cause"] != ""
        assert "Apollo.io" in ea["root_cause"]
        assert len(ea["proposed_solutions"]) >= 2

    def test_clean_run_empty_error_analysis(self, db_session, test_tenant):
        """Clean run with no errors produces empty error_analysis."""
        counters = json.dumps({
            "inserted": 10, "updated": 2, "skipped": 1, "errors": 0,
            "api_diagnostics": [
                {"adapter": "jsearch", "status": "success", "jobs_returned": 13, "error_type": None, "error_message": None},
            ],
        })
        run = JobRun(
            tenant_id=test_tenant.tenant_id,
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

        assert "error_analysis" in result
        assert result["error_analysis"] == []
