"""WarmupAlert model - in-app notification system."""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, Enum
from sqlalchemy.sql import func
import enum

from app.db.base import Base


class AlertType(str, enum.Enum):
    STATUS_CHANGE = 'status_change'
    HEALTH_DROP = 'health_drop'
    BLACKLIST_DETECTED = 'blacklist_detected'
    DNS_ISSUE = 'dns_issue'
    AUTO_PAUSED = 'auto_paused'
    AUTO_RECOVERED = 'auto_recovered'
    WARMUP_COMPLETE = 'warmup_complete'


class AlertSeverity(str, enum.Enum):
    INFO = 'info'
    WARNING = 'warning'
    CRITICAL = 'critical'


class WarmupAlert(Base):
    """In-app warmup notification/alert system."""

    __tablename__ = 'warmup_alerts'

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    mailbox_id = Column(Integer, ForeignKey('sender_mailboxes.mailbox_id'), nullable=True, index=True)
    alert_type = Column(Enum(AlertType, values_callable=lambda x: [e.value for e in x]), nullable=False)
    severity = Column(Enum(AlertSeverity, values_callable=lambda x: [e.value for e in x]), default=AlertSeverity.INFO)
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=True)
    details_json = Column(Text, nullable=True)
    is_read = Column(Boolean, default=False, index=True)
