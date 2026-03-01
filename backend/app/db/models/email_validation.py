"""Email validation results model."""
from datetime import datetime
from enum import Enum as PyEnum
from sqlalchemy import Column, Integer, String, DateTime, Enum, Text, Index, ForeignKey
from app.db.base import Base


class ValidationStatus(str, PyEnum):
    """Email validation status."""
    VALID = "valid"
    INVALID = "invalid"
    CATCH_ALL = "catch_all"
    UNKNOWN = "unknown"


class EmailValidationResult(Base):
    """Email validation results model - Bulk validation responses."""

    __tablename__ = "email_validation_results"

    validation_id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.tenant_id"), nullable=True, index=True)
    email = Column(String(255), nullable=False, index=True)
    provider = Column(String(50), nullable=False)  # neverbounce, zerobounce, hunter, clearout
    status = Column(Enum(ValidationStatus, values_callable=lambda x: [e.value for e in x]), nullable=False)
    sub_status = Column(String(100), nullable=True)  # Provider-specific sub-status
    raw_response_json = Column(Text, nullable=True)  # Full provider response
    validated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index('idx_validation_email', 'email'),
        Index('idx_validation_status', 'status'),
    )

    def __repr__(self) -> str:
        return f"<EmailValidationResult(validation_id={self.validation_id}, email='{self.email}', status='{self.status}')>"
