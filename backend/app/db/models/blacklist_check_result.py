"""BlacklistCheckResult model - DNSBL blacklist monitoring results."""
from sqlalchemy import Column, Integer, String, Boolean, Text, DateTime, ForeignKey
from sqlalchemy.sql import func

from app.db.base import Base


class BlacklistCheckResult(Base):
    """DNSBL blacklist check result per mailbox."""

    __tablename__ = 'blacklist_check_results'

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    mailbox_id = Column(Integer, ForeignKey('sender_mailboxes.mailbox_id'), nullable=False, index=True)
    domain = Column(String(255), nullable=False)
    ip_address = Column(String(45), nullable=True)
    checked_at = Column(DateTime, server_default=func.now())
    results_json = Column(Text, nullable=True)
    total_checked = Column(Integer, default=0)
    total_listed = Column(Integer, default=0)
    is_clean = Column(Boolean, default=True)
