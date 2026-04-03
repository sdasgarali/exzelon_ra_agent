"""Reply macros / quick templates for inbox replies."""
from sqlalchemy import Column, Integer, String, Text, ForeignKey, Index
from app.db.base import Base


class ReplyMacro(Base):
    __tablename__ = "reply_macros"

    macro_id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    body_text = Column(Text, nullable=False)
    body_html = Column(Text, nullable=True)
    category = Column(String(100), nullable=True)  # e.g. "interested", "objection", "followup"
    variables_json = Column(Text, nullable=True)  # JSON array of variable names used
    usage_count = Column(Integer, default=0, nullable=False)
    created_by = Column(Integer, ForeignKey("users.user_id"), nullable=True)

    __table_args__ = (
        Index("idx_macro_tenant", "tenant_id"),
        Index("idx_macro_category", "category"),
    )

    def __repr__(self) -> str:
        return f"<ReplyMacro(macro_id={self.macro_id}, title='{self.title}')>"
