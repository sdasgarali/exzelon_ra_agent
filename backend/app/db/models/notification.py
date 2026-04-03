"""Notification center entries."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean, Index
from app.db.base import Base


class NotificationEntry(Base):
    __tablename__ = "notifications"

    notification_id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=True)  # None = broadcast to all users

    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=True)
    category = Column(String(50), nullable=False)  # campaign/inbox/warmup/system/billing
    priority = Column(String(20), default='normal', nullable=False)  # low/normal/high/urgent
    link = Column(String(500), nullable=True)  # deep link to relevant page

    is_read = Column(Boolean, default=False, nullable=False)
    read_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("idx_notif_tenant_user", "tenant_id", "user_id"),
        Index("idx_notif_category", "category"),
        Index("idx_notif_read", "is_read"),
    )

    def __repr__(self) -> str:
        return f"<NotificationEntry(notification_id={self.notification_id}, title='{self.title}')>"
