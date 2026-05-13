"""Tenant-to-LOB type assignment model.

Maps which LOB types a tenant is allowed to use.
Managed by Super Admin via admin/tenants/{id}/lob-assignments.
"""
from sqlalchemy import (
    Column, Integer, String, ForeignKey,
    Index, UniqueConstraint,
)
from app.db.base import Base


class TenantLOBAssignment(Base):
    """Tracks which LOB types are assigned to each tenant.

    When a tenant has assignment records, only assigned LOB types are visible.
    If a tenant has NO assignment records, all LOBs remain visible (backward compatible).
    """

    __tablename__ = "tenant_lob_assignments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(
        Integer,
        ForeignKey("tenants.tenant_id", ondelete="CASCADE"),
        nullable=False,
    )
    lob_type = Column(String(50), nullable=False)  # matches LOBType enum values
    assigned_by = Column(String(255), nullable=True)  # email of super admin

    __table_args__ = (
        UniqueConstraint("tenant_id", "lob_type", name="uq_tenant_lob_assignment"),
        Index("idx_tla_tenant", "tenant_id"),
    )

    def __repr__(self) -> str:
        return f"<TenantLOBAssignment(id={self.id}, tenant_id={self.tenant_id}, lob_type='{self.lob_type}')>"
