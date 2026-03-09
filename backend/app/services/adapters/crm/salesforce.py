"""Salesforce CRM adapter (REST API)."""
import httpx
import structlog
from typing import Dict, Any, List
from app.core.config import settings
from app.services.adapters.crm.base import CRMAdapter

logger = structlog.get_logger()


class SalesforceAdapter(CRMAdapter):
    """Salesforce CRM integration via REST API."""

    def __init__(self):
        self.instance_url = getattr(settings, "SALESFORCE_INSTANCE_URL", "")
        self.access_token = ""  # Would be obtained via OAuth2 refresh flow

    def _get_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    def sync_contact(self, contact_data: Dict[str, Any]) -> Dict[str, Any]:
        if not self.instance_url:
            return {"success": False, "error": "Salesforce not configured"}
        try:
            with httpx.Client(timeout=10) as client:
                resp = client.post(
                    f"{self.instance_url}/services/data/v59.0/sobjects/Contact",
                    json={
                        "Email": contact_data.get("email", ""),
                        "FirstName": contact_data.get("first_name", ""),
                        "LastName": contact_data.get("last_name", ""),
                        "Title": contact_data.get("title", ""),
                        "Phone": contact_data.get("phone", ""),
                    },
                    headers=self._get_headers(),
                )
                if resp.status_code in (200, 201):
                    return {"crm_id": resp.json().get("id"), "success": True}
                return {"success": False, "error": resp.text[:200]}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def sync_deal(self, deal_data: Dict[str, Any]) -> Dict[str, Any]:
        if not self.instance_url:
            return {"success": False, "error": "Salesforce not configured"}
        try:
            with httpx.Client(timeout=10) as client:
                resp = client.post(
                    f"{self.instance_url}/services/data/v59.0/sobjects/Opportunity",
                    json={
                        "Name": deal_data.get("name", ""),
                        "Amount": deal_data.get("value", 0),
                        "StageName": deal_data.get("stage", ""),
                        "CloseDate": deal_data.get("expected_close_date", ""),
                    },
                    headers=self._get_headers(),
                )
                if resp.status_code in (200, 201):
                    return {"crm_id": resp.json().get("id"), "success": True}
                return {"success": False, "error": resp.text[:200]}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def pull_contacts(self, limit: int = 100) -> List[Dict[str, Any]]:
        if not self.instance_url:
            return []
        return []

    def create_timeline_event(self, crm_id: str, event_data: Dict[str, Any]) -> bool:
        logger.info("Salesforce timeline event", crm_id=crm_id)
        return True
