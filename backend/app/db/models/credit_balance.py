"""Per-tenant credit balance — the authoritative, atomically-decremented counter.

Closes ELR-009b. `check_credit_budget()` previously summed the `credit_usage` ledger
and compared the total to the plan ceiling, which is a read-then-write race: two
concurrent pipeline workers both read "999 used of 1000" and both proceed. Under a
thread pool of six (`pipeline_max_workers`) that overage is routine, not theoretical.

This row is the lock point. Spending takes `SELECT ... FOR UPDATE` on it, so the
check and the decrement happen inside one transaction and concurrent spenders
serialise. The `credit_usage` ledger stays as the append-only audit trail of *what*
the credits went on; this table is the running total.
"""
from datetime import date, datetime

from sqlalchemy import Column, Date, DateTime, Float, ForeignKey, Index, Integer

from app.db.base import Base


class TenantCreditBalance(Base):
    """One row per tenant. Created lazily on first spend or balance read."""

    __tablename__ = "tenant_credit_balances"

    balance_id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(
        Integer,
        ForeignKey("tenants.tenant_id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # First day of the month this allowance covers. When it falls behind the current
    # month the allowance is refilled — lazily on access, and by a scheduler sweep so
    # dormant tenants are also correct.
    period_start = Column(Date, nullable=False, default=lambda: date.today().replace(day=1))

    # Remaining credits from this month's plan grant. Does NOT roll over.
    allowance_credits = Column(Float, nullable=False, default=0.0)

    # Remaining purchased credits. These never expire and are spent only once the
    # monthly allowance is exhausted, so a top-up is never wasted on a month the
    # allowance would have covered anyway.
    topup_credits = Column(Float, nullable=False, default=0.0)

    # Running totals, for reporting without re-aggregating the ledger.
    period_spent = Column(Float, nullable=False, default=0.0)
    lifetime_spent = Column(Float, nullable=False, default=0.0)
    lifetime_purchased = Column(Float, nullable=False, default=0.0)

    last_spend_at = Column(DateTime, nullable=True)
    last_refill_at = Column(DateTime, nullable=True, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_credit_balance_tenant", "tenant_id"),
        Index("idx_credit_balance_period", "period_start"),
    )

    @property
    def total_available(self) -> float:
        return float(self.allowance_credits or 0) + float(self.topup_credits or 0)

    def __repr__(self) -> str:
        return (
            f"<TenantCreditBalance(tenant_id={self.tenant_id}, "
            f"allowance={self.allowance_credits}, topup={self.topup_credits})>"
        )
