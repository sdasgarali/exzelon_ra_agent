"""Login history model for tracking authentication attempts."""
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Index
from app.db.base import Base


class LoginHistory(Base):
    """Records every login attempt (success and failure) for audit/security."""

    __tablename__ = "login_history"

    log_id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.tenant_id"), nullable=True, index=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=True)  # null if email not found
    email_attempted = Column(String(255), nullable=False, index=True)
    success = Column(Boolean, nullable=False, default=False, index=True)
    failure_reason = Column(String(100), nullable=True)  # invalid_credentials, inactive, unverified, locked
    ip_address = Column(String(45), nullable=True)  # IPv4/IPv6
    user_agent = Column(String(500), nullable=True)

    __table_args__ = (
        Index("idx_login_email_created", "email_attempted", "created_at"),
        Index("idx_login_tenant_created", "tenant_id", "created_at"),
        Index("idx_login_ip", "ip_address"),
        Index("idx_login_success_created", "success", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<LoginHistory(log_id={self.log_id}, email='{self.email_attempted}', success={self.success})>"
