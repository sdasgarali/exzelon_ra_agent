"""Job runs model for pipeline execution history."""
from datetime import datetime
from enum import Enum as PyEnum
from sqlalchemy import Column, Integer, String, DateTime, Enum, Text, Index
from app.db.base import Base


class JobStatus(str, PyEnum):
    """Job run status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobRun(Base):
    """Job runs model - Pipeline job execution history."""

    __tablename__ = "job_runs"

    run_id = Column(Integer, primary_key=True, autoincrement=True)
    pipeline_name = Column(String(100), nullable=False)  # lead_sourcing, contact_enrichment, email_validation, outreach
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    ended_at = Column(DateTime, nullable=True)
    status = Column(Enum(JobStatus), default=JobStatus.PENDING, nullable=False)
    counters_json = Column(Text, nullable=True)  # JSON with inserted/updated/skipped counts
    lead_results_json = Column(Text, nullable=True)  # JSON array of per-lead enrichment results
    logs_path = Column(String(500), nullable=True)
    error_message = Column(Text, nullable=True)
    triggered_by = Column(String(100), nullable=True)  # user email or "scheduler"
    progress_pct = Column(Integer, default=0, nullable=False)  # 0-100 progress percentage
    is_cancel_requested = Column(Integer, default=0, nullable=False)  # 0=no, 1=cancel requested

    __table_args__ = (
        Index('idx_job_pipeline', 'pipeline_name'),
        Index('idx_job_status', 'status'),
        Index('idx_job_started_at', 'started_at'),
    )

    def __repr__(self) -> str:
        return f"<JobRun(run_id={self.run_id}, pipeline='{self.pipeline_name}', status='{self.status}')>"
