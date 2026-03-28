"""Automation event model — tracks what the system does behind the scenes."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Index
from app.db.base import Base


class AutomationEvent(Base):
    """Logs automation activity: scheduler runs, AI classifications, campaign sends, etc."""

    __tablename__ = "automation_events"

    event_id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    event_type = Column(String(50), nullable=False, index=True)  # scheduler_run, ai_classify, ai_suggest, campaign_send, reply_detected, inbox_sync
    source = Column(String(50), nullable=False, default="scheduler")  # scheduler, user, api
    title = Column(String(255), nullable=False)  # human-readable: "Campaign processor ran"
    details_json = Column(Text, nullable=True)  # JSON with specifics
    status = Column(String(20), nullable=False, default="success")  # success, error, skipped

    # Override base class created_at to avoid needing updated_at / is_archived for log entries
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    def __repr__(self) -> str:
        return f"<AutomationEvent(event_id={self.event_id}, type='{self.event_type}', title='{self.title}')>"
