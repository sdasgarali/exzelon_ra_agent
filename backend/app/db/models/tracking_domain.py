"""Custom tracking domain model for email tracking."""
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey
from app.db.base import Base


class TrackingDomain(Base):
    """Custom tracking domains for email open/click tracking.

    Users can configure their own domains (e.g., track.company.com) instead
    of using the app's default domain for tracking pixels and click links,
    which improves deliverability.
    """
    __tablename__ = "tracking_domains"

    domain_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    domain_name = Column(String(255), unique=True, nullable=False, index=True)
    is_verified = Column(Boolean, default=False, nullable=False)
    cname_target = Column(String(255), nullable=True)  # The CNAME record value to point to
    is_default = Column(Boolean, default=False, nullable=False)
    mailbox_id = Column(Integer, ForeignKey("sender_mailboxes.mailbox_id"), nullable=True)

    def __repr__(self):
        return f"<TrackingDomain {self.domain_name} verified={self.is_verified}>"
