"""Saved search / smart list model for lead filtering."""
from sqlalchemy import Column, Integer, String, Text, Boolean, ForeignKey
from app.db.base import Base


class SavedSearch(Base):
    """Saved search filters for quick lead list access."""
    __tablename__ = "saved_searches"

    search_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    description = Column(String(500), nullable=True)
    filters_json = Column(Text, nullable=False)  # JSON: {state, industry, job_title, salary_min, ...}
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    is_shared = Column(Boolean, default=False, nullable=False)

    def __repr__(self):
        return f"<SavedSearch {self.name} user={self.user_id}>"
