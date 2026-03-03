"""Shared cancel-check helper for pipeline services."""
from datetime import datetime

import structlog

from app.db.models.job_run import JobRun, JobStatus

logger = structlog.get_logger()


def check_cancel(run_id: int, db) -> bool:
    """Check if cancellation was requested for a pipeline run.

    If ``is_cancel_requested == 1``, sets the job status to CANCELLED,
    records ``ended_at``, commits, and returns ``True``.
    Otherwise returns ``False`` without side-effects.
    """
    job_run = db.query(JobRun).filter(JobRun.run_id == run_id).first()
    if job_run and job_run.is_cancel_requested == 1:
        job_run.status = JobStatus.CANCELLED
        job_run.ended_at = datetime.utcnow()
        db.commit()
        logger.info("Pipeline cancelled by user", run_id=run_id)
        return True
    return False
