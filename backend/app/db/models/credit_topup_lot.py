"""One purchased block of top-up credits, with its own expiry.

Top-ups expire a fixed time after purchase (`CREDIT_TOPUP_VALIDITY_DAYS`), so each
purchase has to be tracked separately — a single running total cannot say which
credits are due to lapse. `TenantCreditBalance.topup_credits` stays the cached sum of
`credits_remaining` over a tenant's live lots: every reader keeps using it, and the
balance row stays the one lock point (lots are only ever changed while it is held).
"""
from sqlalchemy import Column, DateTime, Float, ForeignKey, Index, Integer, String

from app.db.base import Base


class CreditTopupLot(Base):
    __tablename__ = "credit_topup_lots"

    lot_id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(
        Integer,
        ForeignKey("tenants.tenant_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    credits_purchased = Column(Float, nullable=False)
    credits_remaining = Column(Float, nullable=False)
    purchased_at = Column(DateTime, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    # Set when the expiry sweep zeroes the lot; NULL while the lot is live.
    expired_at = Column(DateTime, nullable=True)
    # Stripe Checkout session id, or a description for adopted legacy balances.
    reference_id = Column(String(255), nullable=True)

    __table_args__ = (
        # Spend order (soonest expiry first) and the expiry sweep both scan by this.
        Index("idx_topup_lot_tenant_expiry", "tenant_id", "expires_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<CreditTopupLot(lot_id={self.lot_id}, tenant_id={self.tenant_id}, "
            f"remaining={self.credits_remaining}, expires_at={self.expires_at})>"
        )
