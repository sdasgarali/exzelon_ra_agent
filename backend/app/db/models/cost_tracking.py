"""Cost tracking model for revenue analytics."""
from sqlalchemy import Column, Integer, String, Numeric, Date, Text
from app.db.base import Base


class CostEntry(Base):
    """Track costs per category for ROI analytics."""
    __tablename__ = "cost_entries"

    cost_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    category = Column(String(50), nullable=False, index=True)  # lead_sourcing, contact_discovery, validation, sending
    amount = Column(Numeric(10, 2), nullable=False)
    entry_date = Column(Date, nullable=False, index=True)
    notes = Column(Text, nullable=True)
    user_id = Column(Integer, nullable=True)  # Who entered this cost

    def __repr__(self):
        return f"<CostEntry {self.category} ${self.amount} on {self.entry_date}>"
