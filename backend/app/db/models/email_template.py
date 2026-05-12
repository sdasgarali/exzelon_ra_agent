"""Email template model for outreach campaigns."""
from enum import Enum as PyEnum
from sqlalchemy import Column, Integer, String, Text, Boolean, Enum, ForeignKey, Index
from app.db.base import Base


class TemplateStatus(str, PyEnum):
    """Email template status."""
    ACTIVE = "active"
    INACTIVE = "inactive"


class TemplateCategory(str, PyEnum):
    """Email template category."""
    OUTREACH = "outreach"
    FOLLOWUP = "followup"


class EmailTemplate(Base):
    """Email template model for managing outreach email templates."""

    __tablename__ = "email_templates"

    template_id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.tenant_id"), nullable=False, index=True)

    # Line of Business (nullable — NULL = applies to all LOBs)
    lob_id = Column(Integer, ForeignKey("lines_of_business.lob_id", ondelete="SET NULL"), nullable=True, index=True)
    name = Column(String(255), nullable=False)
    subject = Column(String(500), nullable=False)
    body_html = Column(Text, nullable=False)
    body_text = Column(Text, nullable=True)
    status = Column(Enum(TemplateStatus, values_callable=lambda x: [e.value for e in x]), default=TemplateStatus.INACTIVE, nullable=False)
    category = Column(Enum(TemplateCategory, values_callable=lambda x: [e.value for e in x]), default=TemplateCategory.OUTREACH, nullable=False)
    is_default = Column(Boolean, default=False, nullable=False)
    description = Column(Text, nullable=True)
    industry = Column(String(50), nullable=True)
    goal = Column(String(50), nullable=True)
    is_system = Column(Boolean, default=False, nullable=False)

    __table_args__ = (
        Index("idx_template_tenant", "tenant_id"),
        Index("idx_template_tenant_category_status", "tenant_id", "category", "status"),
    )

    def __repr__(self) -> str:
        return f"<EmailTemplate(template_id={self.template_id}, name='{self.name}', status='{self.status}')>"
