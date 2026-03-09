"""Contact details model for discovered contacts."""
from sqlalchemy import Column, Integer, String, DateTime, Enum, Index, ForeignKey, Text
from sqlalchemy.orm import relationship
from enum import Enum as PyEnum
from app.db.base import Base


class PriorityLevel(str, PyEnum):
    """Contact priority level based on decision-maker hierarchy."""
    P1_JOB_POSTER = "p1_job_poster"
    P2_HR_TA_RECRUITER = "p2_hr_ta_recruiter"
    P3_HR_MANAGER = "p3_hr_manager"
    P4_OPS_LEADER = "p4_ops_leader"
    P5_FUNCTIONAL_MANAGER = "p5_functional_manager"


class OutreachStatus(str, PyEnum):
    """Contact-level outreach status."""
    ACTIVE = "active"
    INACTIVE = "inactive"
    UNSUBSCRIBED = "unsubscribed"


class ContactDetails(Base):
    """Contact details model - Discovered contacts for outreach.

    Each contact is linked to a specific lead (job posting) for targeted outreach.
    """

    __tablename__ = "contact_details"

    contact_id = Column(Integer, primary_key=True, autoincrement=True)
    # Direct link to the lead this contact was discovered for
    lead_id = Column(Integer, ForeignKey('lead_details.lead_id', ondelete='CASCADE'), nullable=True, index=True)

    # Company link (kept for backward compatibility and convenience)
    client_name = Column(String(255), nullable=False, index=True)

    # Contact information
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    title = Column(String(255), nullable=True)
    email = Column(String(255), nullable=False, index=True)
    location_state = Column(String(50), nullable=True)  # 2-letter state code
    phone = Column(String(50), nullable=True)

    # Discovery metadata
    source = Column(String(50), nullable=True)  # apollo, seamless
    priority_level = Column(Enum(PriorityLevel, values_callable=lambda x: [e.value for e in x]), nullable=True)

    # Validation status (denormalized for convenience)
    validation_status = Column(String(50), nullable=True)  # Valid, Invalid, Catch-all, Unknown

    # Last outreach tracking for cooldown enforcement
    last_outreach_date = Column(String(50), nullable=True)

    # Outreach status and unsubscribe tracking
    outreach_status = Column(Enum(OutreachStatus, values_callable=lambda x: [e.value for e in x]), default=OutreachStatus.ACTIVE, nullable=False, server_default="active")
    unsubscribed_at = Column(DateTime, nullable=True)

    # Timezone (resolved from state)
    timezone = Column(String(50), nullable=True)

    # Lead scoring
    lead_score = Column(Integer, nullable=True)
    lead_score_factors_json = Column(Text, nullable=True)
    lead_score_updated_at = Column(DateTime, nullable=True)

    # CRM integration IDs
    hubspot_id = Column(String(50), nullable=True, index=True)
    salesforce_id = Column(String(50), nullable=True, index=True)

    # Relationship to lead
    lead = relationship("LeadDetails", back_populates="contacts")

    __table_args__ = (
        Index('idx_contact_lead', 'lead_id'),
        Index('idx_contact_client', 'client_name'),
        Index('idx_contact_email', 'email'),
        Index('idx_contact_priority', 'priority_level'),
    )

    def __repr__(self) -> str:
        return f"<ContactDetails(contact_id={self.contact_id}, lead_id={self.lead_id}, name='{self.first_name} {self.last_name}', email='{self.email}')>"
