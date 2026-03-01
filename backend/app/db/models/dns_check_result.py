"""DNSCheckResult model - DNS health check results."""
from sqlalchemy import Column, Integer, String, Boolean, Text, DateTime, ForeignKey
from sqlalchemy.sql import func

from app.db.base import Base


class DNSCheckResult(Base):
    """DNS health check result per mailbox."""

    __tablename__ = 'dns_check_results'

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    mailbox_id = Column(Integer, ForeignKey('sender_mailboxes.mailbox_id'), nullable=False, index=True)
    domain = Column(String(255), nullable=False)
    checked_at = Column(DateTime, server_default=func.now())
    spf_record = Column(Text, nullable=True)
    spf_valid = Column(Boolean, default=False)
    dkim_selector = Column(String(100), nullable=True)
    dkim_valid = Column(Boolean, default=False)
    dmarc_record = Column(Text, nullable=True)
    dmarc_valid = Column(Boolean, default=False)
    dmarc_policy = Column(String(50), nullable=True)
    mx_records_json = Column(Text, nullable=True)
    overall_score = Column(Integer, default=0)
