"""Settings model for Admin Panel configuration."""
from datetime import datetime
from enum import Enum as PyEnum
from sqlalchemy import Column, String, DateTime, Text
from app.db.base import Base


class SettingType(str, PyEnum):
    """Setting value type for UI validation."""
    STRING = "string"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    JSON = "json"
    LIST = "list"


class Settings(Base):
    """Settings model - Key-value settings store for Admin Panel."""

    __tablename__ = "settings"

    key = Column(String(100), primary_key=True)
    value_json = Column(Text, nullable=True)  # JSON-serialized value
    type = Column(String(20), nullable=False, default="string")
    description = Column(Text, nullable=True)
    updated_by = Column(String(255), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self) -> str:
        return f"<Settings(key='{self.key}', type='{self.type}')>"
