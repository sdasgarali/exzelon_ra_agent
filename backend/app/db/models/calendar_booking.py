"""Calendar booking tracking."""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Index
from app.db.base import Base


class CalendarBooking(Base):
    __tablename__ = "calendar_bookings"

    booking_id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    contact_id = Column(Integer, ForeignKey("contact_details.contact_id"), nullable=True)
    deal_id = Column(Integer, ForeignKey("deals.deal_id"), nullable=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.campaign_id"), nullable=True)

    provider = Column(String(50), nullable=False)  # calendly/cal_com/manual
    booking_url = Column(String(500), nullable=True)
    event_type = Column(String(100), nullable=True)
    scheduled_at = Column(DateTime, nullable=True)
    duration_minutes = Column(Integer, default=30, nullable=False)
    attendee_email = Column(String(255), nullable=True)
    attendee_name = Column(String(255), nullable=True)
    status = Column(String(20), default='scheduled', nullable=False)  # scheduled/completed/cancelled/no_show
    external_id = Column(String(255), nullable=True)
    notes = Column(Text, nullable=True)

    __table_args__ = (
        Index("idx_booking_tenant", "tenant_id"),
        Index("idx_booking_contact", "contact_id"),
        Index("idx_booking_status", "status"),
    )

    def __repr__(self) -> str:
        return f"<CalendarBooking(booking_id={self.booking_id}, status='{self.status}')>"
