"""AI objection handling templates."""
from sqlalchemy import Column, Integer, String, Text, ForeignKey, Boolean, Index
from app.db.base import Base


class ObjectionTemplate(Base):
    __tablename__ = "objection_templates"

    template_id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    objection_type = Column(String(100), nullable=False)  # budget, timing, authority, need, competitor
    objection_text = Column(Text, nullable=False)  # example objection
    response_text = Column(Text, nullable=False)  # recommended response
    category = Column(String(100), nullable=True)  # industry/product category
    effectiveness_score = Column(Integer, default=50, nullable=False)  # 0-100 based on approval rate
    times_used = Column(Integer, default=0, nullable=False)
    times_approved = Column(Integer, default=0, nullable=False)
    created_by = Column(Integer, ForeignKey("users.user_id"), nullable=True)
    is_system = Column(Boolean, default=False, nullable=False)  # system-provided vs user-created

    __table_args__ = (
        Index("idx_objection_tenant", "tenant_id"),
        Index("idx_objection_type", "objection_type"),
    )

    def __repr__(self) -> str:
        return f"<ObjectionTemplate(template_id={self.template_id}, type='{self.objection_type}')>"
