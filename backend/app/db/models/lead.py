"""Lead details model for job posts and leads."""
from enum import Enum as PyEnum
from sqlalchemy import Column, Integer, String, Date, Numeric, Text, Enum, Index, ForeignKey
from sqlalchemy.orm import relationship
from app.db.base import Base


class LeadStatus(str, PyEnum):
    """Lead processing status."""
    OPEN = "open"
    HUNTING = "hunting"
    CLOSED_HIRED = "closed_hired"
    CLOSED_NOT_HIRED = "closed_not_hired"
    CLOSED_TEST = "closed_test"
    # Legacy statuses (for backward compatibility)
    NEW = "new"
    ENRICHED = "enriched"
    VALIDATED = "validated"
    SENT = "sent"
    SKIPPED = "skipped"


# All statuses that represent a closed lead
CLOSED_STATUSES = [
    LeadStatus.CLOSED_HIRED,
    LeadStatus.CLOSED_NOT_HIRED,
    LeadStatus.CLOSED_TEST,
]


def is_closed_status(status) -> bool:
    """Check if a lead status represents a closed lead."""
    if isinstance(status, LeadStatus):
        return status.value.startswith("closed")
    if isinstance(status, str):
        return status.startswith("closed")
    return False


class LeadDetails(Base):
    """Lead details model - Job posts and lead rows sourced from job boards.

    Each lead represents a job posting, and can have multiple contacts
    discovered for targeted outreach. Supports both legacy one-to-many
    (via contact.lead_id FK) and many-to-many (via junction table).
    """

    __tablename__ = "lead_details"

    lead_id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.tenant_id"), nullable=True, index=True)

    # Company/Client information
    client_name = Column(String(255), nullable=False, index=True)

    # Job information
    job_title = Column(String(255), nullable=False)
    state = Column(String(50), nullable=True)  # 2-letter state code
    posting_date = Column(Date, nullable=True)
    job_link = Column(String(500), nullable=True, unique=True)
    salary_min = Column(Numeric(10, 2), nullable=True)
    salary_max = Column(Numeric(10, 2), nullable=True)
    source = Column(String(50), nullable=True)  # linkedin, indeed, glassdoor, simplyhired

    # Contact information (denormalized - primary contact for quick access)
    first_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)
    contact_title = Column(String(255), nullable=True)
    contact_email = Column(String(255), nullable=True)
    contact_phone = Column(String(50), nullable=True)
    contact_source = Column(String(50), nullable=True)  # apollo, seamless

    # Status tracking
    lead_status = Column(Enum(LeadStatus, values_callable=lambda x: [e.value for e in x]), default=LeadStatus.NEW, nullable=False)
    skip_reason = Column(Text, nullable=True)

    # Research analyst tracking
    ra_name = Column(String(100), nullable=True)

    # Legacy one-to-many relationship (contacts with lead_id FK)
    contacts = relationship("ContactDetails", back_populates="lead", cascade="all, delete-orphan")

    # Many-to-many relationship via junction table
    associated_contacts = relationship(
        "ContactDetails",
        secondary="lead_contact_associations",
        backref="associated_leads",
        viewonly=True
    )

    __table_args__ = (
        Index("idx_lead_client_job", "client_name", "job_title", "state", "posting_date"),
        Index("idx_lead_status", "lead_status"),
        Index("idx_lead_posting_date", "posting_date"),
        Index("idx_lead_status_archived", "lead_status", "is_archived"),
    )

    @property
    def contact_count(self) -> int:
        """Return the number of contacts for this lead."""
        return len(self.contacts) if self.contacts else 0

    def __repr__(self) -> str:
        return f"<LeadDetails(lead_id={self.lead_id}, client='{self.client_name}', job='{self.job_title}', contacts={self.contact_count})>"
