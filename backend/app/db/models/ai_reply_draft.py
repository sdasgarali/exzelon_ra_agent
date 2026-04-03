"""AI Reply Agent drafts for human-in-the-loop approval."""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Index
from app.db.base import Base


class AIReplyDraft(Base):
    __tablename__ = "ai_reply_drafts"

    draft_id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    thread_id = Column(String(255), nullable=False, index=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.campaign_id"), nullable=True)
    contact_id = Column(Integer, ForeignKey("contact_details.contact_id"), nullable=True)
    mailbox_id = Column(Integer, ForeignKey("sender_mailboxes.mailbox_id"), nullable=True)

    # Draft content
    subject = Column(String(500), nullable=True)
    body_html = Column(Text, nullable=False)
    body_text = Column(Text, nullable=True)

    # AI metadata
    intent_detected = Column(String(50), nullable=True)  # interested/objection/question/ooo/unknown
    confidence_score = Column(Integer, default=50, nullable=False)  # 0-100
    ai_model_used = Column(String(100), nullable=True)

    # Status
    status = Column(String(20), default='pending', nullable=False)  # pending/approved/rejected/auto_sent/expired
    approved_by = Column(Integer, ForeignKey("users.user_id"), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    sent_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("idx_draft_thread", "thread_id"),
        Index("idx_draft_status", "status"),
        Index("idx_draft_tenant", "tenant_id"),
    )

    def __repr__(self) -> str:
        return f"<AIReplyDraft(draft_id={self.draft_id}, thread='{self.thread_id}', status='{self.status}')>"
