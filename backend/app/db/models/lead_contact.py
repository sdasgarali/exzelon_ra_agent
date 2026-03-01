"""Lead-Contact many-to-many junction table."""
from sqlalchemy import Column, Integer, ForeignKey, UniqueConstraint, Index
from app.db.base import Base


class LeadContactAssociation(Base):
    """Junction table for many-to-many relationship between leads and contacts.

    A contact can be associated with multiple leads (e.g., same HR person at a company
    with multiple job openings), and a lead can have multiple contacts.
    """

    __tablename__ = "lead_contact_associations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    lead_id = Column(Integer, ForeignKey('lead_details.lead_id', ondelete='CASCADE'), nullable=False)
    contact_id = Column(Integer, ForeignKey('contact_details.contact_id', ondelete='CASCADE'), nullable=False)

    __table_args__ = (
        UniqueConstraint('lead_id', 'contact_id', name='uq_lead_contact'),
        Index('idx_lca_lead_id', 'lead_id'),
        Index('idx_lca_contact_id', 'contact_id'),
    )

    def __repr__(self) -> str:
        return f"<LeadContactAssociation(id={self.id}, lead_id={self.lead_id}, contact_id={self.contact_id})>"
