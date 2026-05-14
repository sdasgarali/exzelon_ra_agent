"""Company exclusion model for blocking specific companies from lead sourcing."""
import re
from sqlalchemy import (
    Column, Integer, String, Text, Boolean, ForeignKey,
    Index, UniqueConstraint,
)
from app.db.base import Base


# Reuse the same normalization logic as lead_sourcing dedup
COMPANY_SUFFIXES = [
    r",?\s*(inc\.?|incorporated)$",
    r",?\s*(llc|l\.l\.c\.)$",
    r",?\s*(ltd\.?|limited)$",
    r",?\s*(corp\.?|corporation)$",
    r",?\s*(co\.?)$",
    r",?\s*company$",
    r",?\s*holdings$",
    r",?\s*group$",
    r",?\s*enterprises?$",
    r",?\s*services?$",
    r",?\s*solutions?$",
    r",?\s*technologies$",
    r",?\s*international$",
    r",?\s*partners?$",
    r",?\s*associates?$",
    r",?\s*consulting$",
    r",?\s*&\s*co\.?$",
]


def normalize_company_for_exclusion(name: str) -> str:
    """Normalize company name for matching during exclusion checks."""
    if not name:
        return ""
    normalized = name.lower().strip()
    if normalized.startswith("the "):
        normalized = normalized[4:]
    for pattern in COMPANY_SUFFIXES:
        normalized = re.sub(pattern, '', normalized, flags=re.IGNORECASE)
    normalized = re.sub(r'[^\w\s]', '', normalized)
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    return normalized


class CompanyExclusion(Base):
    """Excluded company — leads from these companies are skipped during sourcing.

    Tenant-scoped, optionally LOB-scoped. Each row represents one company
    that should be excluded. The is_active flag allows toggling exclusions
    on/off without deleting them (supports "select all / unselect all").
    """

    __tablename__ = "company_exclusions"

    exclusion_id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(
        Integer,
        ForeignKey("tenants.tenant_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    lob_id = Column(
        Integer,
        ForeignKey("lines_of_business.lob_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    company_name = Column(String(255), nullable=False)
    company_name_normalized = Column(String(255), nullable=False, index=True)
    category = Column(String(100), nullable=True)  # e.g. "IT Staffing", "Healthcare Staffing"
    is_active = Column(Boolean, default=True, nullable=False, index=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "company_name_normalized", name="uq_exclusion_tenant_company"),
        Index("idx_excl_tenant_active", "tenant_id", "is_active"),
        Index("idx_excl_tenant_lob", "tenant_id", "lob_id"),
    )

    def __repr__(self) -> str:
        return f"<CompanyExclusion(id={self.exclusion_id}, company='{self.company_name}', active={self.is_active})>"
