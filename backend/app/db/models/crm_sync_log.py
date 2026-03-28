"""CRM sync log model for tracking bidirectional sync operations."""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Index
from sqlalchemy.sql import func
from app.db.base import Base


class CRMSyncLog(Base):
    """Log of CRM sync operations."""
    __tablename__ = "crm_sync_logs"

    sync_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    crm_type = Column(String(50), nullable=False)  # hubspot, salesforce
    direction = Column(String(10), nullable=False)  # pull, push
    entity_type = Column(String(50), nullable=False)  # contacts, deals
    records_synced = Column(Integer, default=0)
    errors = Column(Text, nullable=True)
    started_at = Column(DateTime, server_default=func.now())
    completed_at = Column(DateTime, nullable=True)

    def __repr__(self):
        return f"<CRMSyncLog {self.crm_type} {self.direction} {self.entity_type}>"
