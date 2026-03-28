"""Settings schemas."""
from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel


class SettingUpdate(BaseModel):
    """Schema for updating a setting."""
    value: Any = None
    value_json: Optional[str] = None  # Allow raw JSON string
    type: Optional[str] = None
    description: Optional[str] = None


class SettingResponse(BaseModel):
    """Schema for setting response."""
    key: str
    value_json: Optional[str] = None
    type: str
    description: Optional[str] = None
    updated_by: Optional[str] = None
    updated_at: datetime
    is_tenant_override: bool = False

    class Config:
        from_attributes = True
