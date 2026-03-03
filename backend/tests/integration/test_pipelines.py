"""Integration tests for pipeline endpoints."""
import pytest

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
