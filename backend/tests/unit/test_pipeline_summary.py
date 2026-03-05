"""Unit tests for pipeline summary scoring and fallback generation."""
import json
import pytest
from unittest.mock import patch, MagicMock

from app.services.pipeline_summary import calculate_success_score, generate_pipeline_summary, _fallback_summary
from app.db.models.job_run import JobRun, JobStatus


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
        """When no AI adapter is configured, returns valid fallback dict."""
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
