"""Integration tests for pipeline endpoints."""
import pytest


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
