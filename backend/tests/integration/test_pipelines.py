"""Integration tests for pipeline endpoints."""
import json
import pytest
from unittest.mock import patch

from app.db.models.job_run import JobRun, JobStatus


class TestPipelineEndpoints:
    """Tests for /api/v1/pipelines endpoints."""

    def test_list_pipeline_runs(self, client, auth_headers, sample_job_run):
        """Test listing pipeline runs."""
        response = client.get("/api/v1/pipelines/runs", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert data[0]["pipeline_name"] == "lead_sourcing"

    def test_get_run_detail(self, client, auth_headers, sample_job_run):
        """Test getting a single pipeline run by ID."""
        response = client.get(
            f"/api/v1/pipelines/runs/{sample_job_run.run_id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["run_id"] == sample_job_run.run_id
        assert data["status"] == "completed"
        assert data["records_processed"] > 0

    def test_run_not_found(self, client, auth_headers):
        """Test 404 for missing pipeline run."""
        response = client.get("/api/v1/pipelines/runs/99999", headers=auth_headers)
        assert response.status_code == 404

    def test_unauthenticated_access(self, client):
        """Test 401 without token."""
        response = client.get("/api/v1/pipelines/runs")
        assert response.status_code == 401

    def test_run_list_includes_cancel_fields(self, client, auth_headers, sample_job_run):
        """Test that run list response includes is_cancel_requested and progress_pct."""
        response = client.get("/api/v1/pipelines/runs", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        first_run = data[0]
        assert "is_cancel_requested" in first_run
        assert "progress_pct" in first_run
        assert first_run["is_cancel_requested"] is False
        assert isinstance(first_run["progress_pct"], int)

    def test_run_detail_includes_cancel_fields(self, client, auth_headers, sample_job_run):
        """Test that run detail response includes is_cancel_requested and progress_pct."""
        response = client.get(
            f"/api/v1/pipelines/runs/{sample_job_run.run_id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "is_cancel_requested" in data
        assert "progress_pct" in data


class TestCancelEndpoint:
    """Tests for POST /api/v1/pipelines/jobs/{run_id}/cancel."""

    def test_cancel_running_job(self, client, auth_headers, db_session):
        """Admin can cancel a running job."""
        run = JobRun(
            pipeline_name="lead_sourcing",
            status=JobStatus.RUNNING,
            triggered_by="admin@test.com",
        )
        db_session.add(run)
        db_session.commit()

        response = client.post(
            f"/api/v1/pipelines/jobs/{run.run_id}/cancel",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["run_id"] == run.run_id
        assert "Cancellation requested" in data["message"]

        db_session.refresh(run)
        assert run.is_cancel_requested == 1

    def test_cancel_completed_job_fails(self, client, auth_headers, sample_job_run):
        """Cannot cancel a completed job (400)."""
        response = client.post(
            f"/api/v1/pipelines/jobs/{sample_job_run.run_id}/cancel",
            headers=auth_headers,
        )
        assert response.status_code == 400

    def test_cancel_nonexistent_job(self, client, auth_headers):
        """Cannot cancel a job that doesn't exist (404)."""
        response = client.post(
            "/api/v1/pipelines/jobs/99999/cancel",
            headers=auth_headers,
        )
        assert response.status_code == 404

    def test_viewer_cannot_cancel(self, client, viewer_headers, db_session):
        """Viewer role cannot cancel jobs (403)."""
        run = JobRun(
            pipeline_name="lead_sourcing",
            status=JobStatus.RUNNING,
            triggered_by="admin@test.com",
        )
        db_session.add(run)
        db_session.commit()

        response = client.post(
            f"/api/v1/pipelines/jobs/{run.run_id}/cancel",
            headers=viewer_headers,
        )
        assert response.status_code == 403


class TestRunSummaryEndpoint:
    """Tests for GET /api/v1/pipelines/runs/{run_id}/summary."""

    def test_get_summary_completed_run(self, client, auth_headers, db_session):
        """Completed run returns valid enhanced summary structure."""
        run = JobRun(
            pipeline_name="lead_sourcing",
            status=JobStatus.COMPLETED,
            counters_json='{"inserted": 10, "updated": 2, "skipped": 1, "errors": 0}',
            triggered_by="admin@test.com",
        )
        db_session.add(run)
        db_session.commit()

        with patch("app.services.warmup.content_generator.get_ai_adapter", return_value=None):
            response = client.get(
                f"/api/v1/pipelines/runs/{run.run_id}/summary",
                headers=auth_headers,
            )
        assert response.status_code == 200
        data = response.json()
        # Existing fields
        assert "success_score" in data
        assert "summary" in data
        assert "suggestions" in data
        assert "highlights" in data
        assert "generated_at" in data
        assert "ai_generated" in data
        assert isinstance(data["success_score"], int)
        assert 0 <= data["success_score"] <= 100
        # Enhanced fields
        assert "run_metadata" in data
        assert "source_breakdown" in data
        assert "api_diagnostics" in data
        assert "counters" in data
        assert data["run_metadata"]["pipeline_name"] == "lead_sourcing"
        assert data["run_metadata"]["pipeline_label"] == "Lead Sourcing"
        assert isinstance(data["source_breakdown"], list)
        assert isinstance(data["api_diagnostics"], list)

    def test_summary_cached_on_second_call(self, client, auth_headers, db_session):
        """Second call returns same cached summary (same generated_at)."""
        run = JobRun(
            pipeline_name="email_validation",
            status=JobStatus.COMPLETED,
            counters_json='{"validated": 10, "valid": 8, "invalid": 2, "errors": 0}',
            triggered_by="admin@test.com",
        )
        db_session.add(run)
        db_session.commit()

        with patch("app.services.warmup.content_generator.get_ai_adapter", return_value=None):
            resp1 = client.get(f"/api/v1/pipelines/runs/{run.run_id}/summary", headers=auth_headers)
            resp2 = client.get(f"/api/v1/pipelines/runs/{run.run_id}/summary", headers=auth_headers)

        assert resp1.status_code == 200
        assert resp2.status_code == 200
        assert resp1.json()["generated_at"] == resp2.json()["generated_at"]

    def test_summary_regenerate_param(self, client, auth_headers, db_session):
        """?regenerate=true forces fresh generation even when cached."""
        run = JobRun(
            pipeline_name="lead_sourcing",
            status=JobStatus.COMPLETED,
            counters_json='{"inserted": 5, "updated": 0, "skipped": 0, "errors": 0}',
            triggered_by="admin@test.com",
        )
        db_session.add(run)
        db_session.commit()

        with patch("app.services.warmup.content_generator.get_ai_adapter", return_value=None):
            # First call caches
            resp1 = client.get(f"/api/v1/pipelines/runs/{run.run_id}/summary", headers=auth_headers)
            gen1 = resp1.json()["generated_at"]

            # Second call with regenerate=true gets fresh result
            resp2 = client.get(
                f"/api/v1/pipelines/runs/{run.run_id}/summary?regenerate=true",
                headers=auth_headers,
            )
            gen2 = resp2.json()["generated_at"]

        assert resp2.status_code == 200
        # generated_at should differ (regenerated)
        assert gen1 != gen2

    def test_summary_old_format_auto_regenerates(self, client, auth_headers, db_session):
        """Old-format cached summary (missing source_breakdown) is auto-regenerated."""
        old_summary = json.dumps({
            "success_score": 80,
            "summary": "Old format summary.",
            "suggestions": ["old suggestion"],
            "highlights": ["old highlight"],
            "generated_at": "2026-01-01T00:00:00Z",
            "ai_generated": False,
        })
        run = JobRun(
            pipeline_name="lead_sourcing",
            status=JobStatus.COMPLETED,
            counters_json='{"inserted": 10, "updated": 0, "skipped": 0, "errors": 0}',
            summary_json=old_summary,
            triggered_by="admin@test.com",
        )
        db_session.add(run)
        db_session.commit()

        with patch("app.services.warmup.content_generator.get_ai_adapter", return_value=None):
            response = client.get(
                f"/api/v1/pipelines/runs/{run.run_id}/summary",
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        # Should have been regenerated with new fields
        assert "source_breakdown" in data
        assert "api_diagnostics" in data
        assert "run_metadata" in data
        # generated_at should be different from old cached
        assert data["generated_at"] != "2026-01-01T00:00:00Z"

    def test_summary_running_run_returns_400(self, client, auth_headers, db_session):
        """In-progress runs return 400."""
        run = JobRun(
            pipeline_name="contact_enrichment",
            status=JobStatus.RUNNING,
            triggered_by="admin@test.com",
        )
        db_session.add(run)
        db_session.commit()

        response = client.get(
            f"/api/v1/pipelines/runs/{run.run_id}/summary",
            headers=auth_headers,
        )
        assert response.status_code == 400

    def test_summary_not_found(self, client, auth_headers):
        """Nonexistent run returns 404."""
        response = client.get(
            "/api/v1/pipelines/runs/99999/summary",
            headers=auth_headers,
        )
        assert response.status_code == 404

    def test_summary_unauthenticated(self, client):
        """Unauthenticated request returns 401."""
        response = client.get("/api/v1/pipelines/runs/1/summary")
        assert response.status_code == 401

    def test_summary_failed_run(self, client, auth_headers, db_session):
        """Failed runs get score 0 and include error info."""
        run = JobRun(
            pipeline_name="outreach",
            status=JobStatus.FAILED,
            counters_json='{"sent": 0, "total": 10, "errors": 10}',
            error_message="SMTP auth failed",
            triggered_by="admin@test.com",
        )
        db_session.add(run)
        db_session.commit()

        with patch("app.services.warmup.content_generator.get_ai_adapter", return_value=None):
            response = client.get(
                f"/api/v1/pipelines/runs/{run.run_id}/summary",
                headers=auth_headers,
            )
        assert response.status_code == 200
        data = response.json()
        assert data["success_score"] == 0
        assert "run_metadata" in data
        assert data["run_metadata"]["status"] == "failed"
