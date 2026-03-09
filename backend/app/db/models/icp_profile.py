"""Ideal Customer Profile (ICP) model for AI-driven targeting."""
from sqlalchemy import Column, Integer, String, Text, ForeignKey
from app.db.base import Base


class ICPProfile(Base):
    """AI-generated Ideal Customer Profile for lead targeting."""
    __tablename__ = "icp_profiles"

    icp_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    industries_json = Column(Text, nullable=True)  # JSON array of industries
    job_titles_json = Column(Text, nullable=True)   # JSON array of job titles
    states_json = Column(Text, nullable=True)        # JSON array of US states
    company_sizes_json = Column(Text, nullable=True) # JSON array like ["1-50", "51-200"]
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)

    def __repr__(self):
        return f"<ICPProfile {self.name}>"
