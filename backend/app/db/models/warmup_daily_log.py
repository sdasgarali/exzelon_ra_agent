"""WarmupDailyLog model - daily snapshot per mailbox for time-series analytics."""
from sqlalchemy import Column, Integer, Float, String, Boolean, Date, DateTime, ForeignKey
from sqlalchemy.sql import func

from app.db.base import Base


class WarmupDailyLog(Base):
    """Daily snapshot per mailbox for time-series analytics."""

    __tablename__ = 'warmup_daily_logs'

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    mailbox_id = Column(Integer, ForeignKey('sender_mailboxes.mailbox_id'), nullable=False, index=True)
    log_date = Column(Date, nullable=False, index=True)
    emails_sent = Column(Integer, default=0)
    emails_received = Column(Integer, default=0)
    opens = Column(Integer, default=0)
    replies = Column(Integer, default=0)
    bounces = Column(Integer, default=0)
    health_score = Column(Float, default=0.0)
    warmup_day = Column(Integer, default=0)
    phase = Column(Integer, default=0)
    daily_limit = Column(Integer, default=0)
    bounce_rate = Column(Float, default=0.0)
    reply_rate = Column(Float, default=0.0)
    complaint_rate = Column(Float, default=0.0)
    dns_spf_valid = Column(Boolean, nullable=True)
    dns_dkim_valid = Column(Boolean, nullable=True)
    dns_dmarc_valid = Column(Boolean, nullable=True)
    blacklisted = Column(Boolean, default=False)
    blacklist_count = Column(Integer, default=0)
