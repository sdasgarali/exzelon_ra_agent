"""One turn of a user's AI Copilot conversation.

The copilot remembers each user's conversation across reloads and sessions, so every
user and assistant turn is stored here. Rows are private to their author: they are
always read with BOTH ``tenant_id`` and ``user_id`` — never by tenant alone, since
teammates must not see each other's chats.
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text

from app.db.base import Base


class CopilotMessage(Base):
    __tablename__ = "copilot_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(
        Integer,
        ForeignKey("tenants.tenant_id", ondelete="CASCADE"),
        # NULL = a global super admin chatting with no workspace selected.
        nullable=True,
        index=True,
    )
    user_id = Column(
        Integer,
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role = Column(String(16), nullable=False)  # 'user' | 'assistant'
    content = Column(Text, nullable=False)
    # Page the user was on when they asked (free text from the client, truncated).
    context_page = Column(String(64), nullable=True)
    # Overrides Base.created_at only to add an index: history is read newest-first.
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    __table_args__ = (
        # History load: WHERE tenant_id=? AND user_id=? ORDER BY created_at, id.
        Index("idx_copilot_msg_tenant_user_created", "tenant_id", "user_id", "created_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<CopilotMessage(id={self.id}, tenant_id={self.tenant_id}, "
            f"user_id={self.user_id}, role={self.role})>"
        )
