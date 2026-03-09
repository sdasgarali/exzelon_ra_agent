"""HubSpot CRM adapter (API v3)."""
import httpx
import structlog
from typing import Dict, Any, List
from app.core.config import settings
from app.services.adapters.crm.base import CRMAdapter

logger = structlog.get_logger()

HUBSPOT_API_BASE = "https://api.hubapi.com"


class HubSpotAdapter(CRMAdapter):
    """HubSpot CRM integration via API v3."""

    def __init__(self):
        self.api_key = getattr(settings, "HUBSPOT_API_KEY", "")
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def sync_contact(self, contact_data: Dict[str, Any]) -> Dict[str, Any]:
        if not self.api_key:
            return {"success": False, "error": "HubSpot API key not configured"}
        try:
            with httpx.Client(timeout=10) as client:
                resp = client.post(
                    f"{HUBSPOT_API_BASE}/crm/v3/objects/contacts",
                    json={"properties": {
                        "email": contact_data.get("email", ""),
                        "firstname": contact_data.get("first_name", ""),
                        "lastname": contact_data.get("last_name", ""),
                        "company": contact_data.get("company", ""),
                        "jobtitle": contact_data.get("title", ""),
                        "phone": contact_data.get("phone", ""),
                    }},
                    headers=self.headers,
                )
                if resp.status_code in (200, 201):
                    return {"crm_id": resp.json().get("id"), "success": True}
                return {"success": False, "error": resp.text[:200]}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def sync_deal(self, deal_data: Dict[str, Any]) -> Dict[str, Any]:
        if not self.api_key:
            return {"success": False, "error": "HubSpot API key not configured"}
        try:
            with httpx.Client(timeout=10) as client:
                resp = client.post(
                    f"{HUBSPOT_API_BASE}/crm/v3/objects/deals",
                    json={"properties": {
                        "dealname": deal_data.get("name", ""),
                        "amount": str(deal_data.get("value", 0)),
                        "dealstage": deal_data.get("stage", ""),
                    }},
                    headers=self.headers,
                )
                if resp.status_code in (200, 201):
                    return {"crm_id": resp.json().get("id"), "success": True}
                return {"success": False, "error": resp.text[:200]}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def pull_contacts(self, limit: int = 100) -> List[Dict[str, Any]]:
        if not self.api_key:
            return []
        try:
            with httpx.Client(timeout=10) as client:
                resp = client.get(
                    f"{HUBSPOT_API_BASE}/crm/v3/objects/contacts",
                    params={"limit": limit},
                    headers=self.headers,
                )
                if resp.status_code == 200:
                    return resp.json().get("results", [])
        except Exception as e:
            logger.error("HubSpot pull contacts failed", error=str(e))
        return []

    def create_timeline_event(self, crm_id: str, event_data: Dict[str, Any]) -> bool:
        logger.info("HubSpot timeline event", crm_id=crm_id, event=event_data)
        return True
