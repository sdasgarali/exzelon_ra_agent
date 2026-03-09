"""Abstract base class for CRM adapters."""
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional


class CRMAdapter(ABC):
    """Base class for CRM integrations (HubSpot, Salesforce, etc.)."""

    @abstractmethod
    def sync_contact(self, contact_data: Dict[str, Any]) -> Dict[str, Any]:
        """Push a contact to the CRM. Returns {crm_id, success, error}."""
        ...

    @abstractmethod
    def sync_deal(self, deal_data: Dict[str, Any]) -> Dict[str, Any]:
        """Push a deal to the CRM. Returns {crm_id, success, error}."""
        ...

    @abstractmethod
    def pull_contacts(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Pull contacts from the CRM."""
        ...

    @abstractmethod
    def create_timeline_event(self, crm_id: str, event_data: Dict[str, Any]) -> bool:
        """Create a timeline/activity event on a CRM record."""
        ...
