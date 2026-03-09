"""Inbox placement seed testing models."""
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, DateTime, Boolean,
    ForeignKey, Index,
)
from app.db.base import Base


class SeedTestAccount(Base):
    """Seed email account for inbox placement testing."""

    __tablename__ = "seed_test_accounts"

    account_id = Column(Integer, primary_key=True, autoincrement=True)
    provider = Column(String(50), nullable=False)  # gmail/outlook/yahoo
    email = Column(String(255), nullable=False, unique=True)
    imap_password = Column(String(500), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)

    def __repr__(self) -> str:
        return f"<SeedTestAccount(account_id={self.account_id}, email='{self.email}')>"


class SeedTestResult(Base):
    """Result of an inbox placement test."""

    __tablename__ = "seed_test_results"

    result_id = Column(Integer, primary_key=True, autoincrement=True)
    mailbox_id = Column(Integer, ForeignKey("sender_mailboxes.mailbox_id"), nullable=False)
    test_run_id = Column(String(50), nullable=False)
    seed_account_id = Column(Integer, ForeignKey("seed_test_accounts.account_id"), nullable=False)
    placement = Column(String(50), nullable=True)  # inbox/spam/promotions/not_delivered
    checked_at = Column(DateTime, nullable=True)
    latency_seconds = Column(Integer, nullable=True)

    __table_args__ = (
        Index("idx_seed_result_mailbox", "mailbox_id"),
        Index("idx_seed_result_run", "test_run_id"),
    )

    def __repr__(self) -> str:
        return f"<SeedTestResult(result_id={self.result_id}, placement='{self.placement}')>"
