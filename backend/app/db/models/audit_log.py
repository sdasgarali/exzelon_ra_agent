"""Audit log model for tracking entity changes."""
from sqlalchemy import Column, Integer, String, Text, Index
from app.db.base import Base


class AuditLog(Base):
    """Records who changed what, when, and how."""

    __tablename__ = "audit_logs"

    log_id = Column(Integer, primary_key=True, autoincrement=True)
    entity_type = Column(String(50), nullable=False)   # e.g. "lead", "contact", "mailbox"
    entity_id = Column(Integer, nullable=False)
    action = Column(String(50), nullable=False)         # e.g. "status_change", "archive", "create", "update", "delete"
    changed_fields = Column(Text, nullable=True)        # JSON: {"field": {"old": ..., "new": ...}}
    changed_by = Column(String(100), nullable=True)     # user email or "system"
    notes = Column(Text, nullable=True)

    __table_args__ = (
        Index("idx_audit_entity", "entity_type", "entity_id"),
        Index("idx_audit_action", "action"),
        Index("idx_audit_changed_by", "changed_by"),
    )

    def __repr__(self) -> str:
        return f"<AuditLog(log_id={self.log_id}, entity={self.entity_type}:{self.entity_id}, action={self.action})>"
