"""Unit tests for the pipeline cancel helper."""
import pytest
from datetime import datetime

from app.db.models.job_run import JobRun, JobStatus
from app.services.pipelines.cancel_helper import check_cancel


class TestCheckCancel:
    """Tests for check_cancel() helper function."""

    def test_returns_true_when_cancel_requested(self, db_session):
        """When is_cancel_requested == 1, sets CANCELLED and returns True."""
        run = JobRun(
            pipeline_name="lead_sourcing",
            status=JobStatus.RUNNING,
            triggered_by="admin@test.com",
            is_cancel_requested=1,
        )
        db_session.add(run)
        db_session.commit()

        result = check_cancel(run.run_id, db_session)

        assert result is True
        db_session.refresh(run)
        assert run.status == JobStatus.CANCELLED
        assert run.ended_at is not None

    def test_returns_false_when_not_requested(self, db_session):
        """When is_cancel_requested == 0, returns False without changes."""
        run = JobRun(
            pipeline_name="lead_sourcing",
            status=JobStatus.RUNNING,
            triggered_by="admin@test.com",
            is_cancel_requested=0,
        )
        db_session.add(run)
        db_session.commit()

        result = check_cancel(run.run_id, db_session)

        assert result is False
        db_session.refresh(run)
        assert run.status == JobStatus.RUNNING
        assert run.ended_at is None

    def test_returns_false_for_nonexistent_run(self, db_session):
        """Returns False when run_id doesn't exist."""
        result = check_cancel(99999, db_session)
        assert result is False
