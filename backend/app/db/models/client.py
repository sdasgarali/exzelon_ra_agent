"""Client info model for company lifecycle tracking."""
from enum import Enum as PyEnum
from sqlalchemy import Column, Integer, String, Date, DateTime, Enum
from app.db.base import Base


class ClientStatus(str, PyEnum):
    """Client status."""
    ACTIVE = "active"
    INACTIVE = "inactive"


class ClientCategory(str, PyEnum):
    """Client category based on posting frequency."""
    REGULAR = "regular"  # unique posting_date count > 3 in last 3 months
    OCCASIONAL = "occasional"
    PROSPECT = "prospect"
    DORMANT = "dormant"


class ClientInfo(Base):
    """Client info model - Per-company lifecycle tracking and categorization."""

    __tablename__ = "client_info"

    client_id = Column(Integer, primary_key=True, autoincrement=True)
    client_name = Column(String(255), unique=True, nullable=False, index=True)
    status = Column(Enum(ClientStatus, values_callable=lambda x: [e.value for e in x]), default=ClientStatus.ACTIVE, nullable=False)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    client_category = Column(Enum(ClientCategory, values_callable=lambda x: [e.value for e in x]), default=ClientCategory.PROSPECT, nullable=False)
    service_count = Column(Integer, default=0, nullable=False)

    # Additional fields for tracking
    industry = Column(String(100), nullable=True)
    company_size = Column(String(50), nullable=True)  # e.g., "1-50", "51-200", "201-500"
    location_state = Column(String(50), nullable=True)

    # Enrichment fields
    website = Column(String(500), nullable=True)
    linkedin_url = Column(String(500), nullable=True)
    domain = Column(String(255), nullable=True)
    description = Column(String(2000), nullable=True)
    logo_url = Column(String(500), nullable=True)
    employee_count = Column(Integer, nullable=True)
    founded_year = Column(Integer, nullable=True)
    headquarters = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=True)
    enrichment_source = Column(String(100), nullable=True)
    enriched_at = Column(DateTime, nullable=True)

    def __repr__(self) -> str:
        return f"<ClientInfo(client_id={self.client_id}, name='{self.client_name}', category='{self.client_category}')>"
