"""Website visitor tracking model (Phase 4)."""
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, DateTime, Text,
    ForeignKey, Index,
)
from app.db.base import Base


class VisitorEvent(Base):
    """Tracks website visitor page views."""

    __tablename__ = "visitor_events"

    event_id = Column(Integer, primary_key=True, autoincrement=True)
    visitor_id = Column(String(100), nullable=False, index=True)  # cookie-based ID
    contact_id = Column(Integer, ForeignKey("contact_details.contact_id"), nullable=True)
    page_url = Column(String(1000), nullable=False)
    referrer = Column(String(1000), nullable=True)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)
    company_name = Column(String(255), nullable=True)  # from reverse IP lookup
    company_domain = Column(String(255), nullable=True)
    metadata_json = Column(Text, nullable=True)
    visited_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_visitor_id", "visitor_id"),
        Index("idx_visitor_contact", "contact_id"),
        Index("idx_visitor_visited", "visited_at"),
    )

    def __repr__(self) -> str:
        return f"<VisitorEvent(event_id={self.event_id}, visitor='{self.visitor_id}')>"
