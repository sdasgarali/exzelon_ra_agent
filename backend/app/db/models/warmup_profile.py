"""WarmupProfile model - custom warmup profiles/presets."""
from sqlalchemy import Column, Integer, String, Boolean, Text, DateTime
from sqlalchemy.sql import func

from app.db.base import Base


class WarmupProfile(Base):
    """Custom warmup profiles/presets."""

    __tablename__ = 'warmup_profiles'

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(100), unique=True, nullable=False)
    description = Column(Text, nullable=True)
    is_default = Column(Boolean, default=False)
    is_system = Column(Boolean, default=False)
    config_json = Column(Text, nullable=False)
