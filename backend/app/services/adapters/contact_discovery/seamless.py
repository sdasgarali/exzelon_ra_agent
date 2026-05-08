"""Seamless.ai contact discovery adapter."""
from typing import List, Dict, Any, Optional
import httpx
from app.services.adapters.base import ContactDiscoveryAdapter
from app.core.config import settings
from app.db.models.contact import PriorityLevel


class SeamlessAdapter(ContactDiscoveryAdapter):
    """Adapter for Seamless.ai contact discovery API."""

    BASE_URL = "https://api.seamless.ai/v1"

    def __init__(self, api_key: str = None):
        self.api_key = api_key or settings.SEAMLESS_API_KEY

    def test_connection(self) -> bool:
        """Test connection to Seamless API."""
        if not self.api_key:
            return False

        try:
            with httpx.Client() as client:
                response = client.get(
                    f"{self.BASE_URL}/account",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    timeout=10
                )
                return response.status_code == 200
        except Exception:
            return False

    def _determine_priority(self, title: str) -> PriorityLevel:
        """Determine priority level based on job title."""
        title_lower = (title or "").lower()

        if any(kw in title_lower for kw in ["hiring manager", "talent acquisition"]):
            return PriorityLevel.P1_JOB_POSTER

        if any(kw in title_lower for kw in ["recruiter", "hr coordinator", "talent"]):
            return PriorityLevel.P2_HR_TA_RECRUITER

        if any(kw in title_lower for kw in ["hr manager", "hrbp", "hr director", "vp hr"]):
            return PriorityLevel.P3_HR_MANAGER

        if any(kw in title_lower for kw in ["operations", "plant manager", "production"]):
            return PriorityLevel.P4_OPS_LEADER

        return PriorityLevel.P5_FUNCTIONAL_MANAGER

    def search_contacts(
        self,
        company_name: str,
        job_title: Optional[str] = None,
        state: Optional[str] = None,
        titles: Optional[List[str]] = None,
        limit: int = 4,
        domain: Optional[str] = None,
        **kwargs,
    ) -> List[Dict[str, Any]]:
        """Search for contacts at a company using Seamless API."""
        if not self.api_key:
            raise ValueError("Seamless API key not configured")

        # Prefer domain for precise matching, fall back to company name
        payload = {
            "limit": limit * 2
        }
        if domain:
            payload["company_domain"] = domain
        else:
            payload["company_name"] = company_name

        # Only apply title filter when explicitly passed by caller
        if titles:
            payload["job_titles"] = titles

        try:
            with httpx.Client() as client:
                response = client.post(
                    f"{self.BASE_URL}/contacts/search",
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {self.api_key}"
                    },
                    json=payload,
                    timeout=30
                )
                response.raise_for_status()
                data = response.json()

                contacts = []
                for person in data.get("contacts", [])[:limit]:
                    contact = self.normalize(person)
                    if contact:
                        contacts.append(contact)

                return contacts

        except Exception as e:
            raise RuntimeError(f"Seamless API error: {str(e)}")

    def normalize(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize Seamless API response to standard format."""
        if not raw_data:
            return None

        email = raw_data.get("email") or raw_data.get("work_email")
        if not email:
            return None

        title = raw_data.get("job_title", "")

        return {
            "first_name": raw_data.get("first_name", ""),
            "last_name": raw_data.get("last_name", ""),
            "title": title,
            "email": email,
            "phone": raw_data.get("phone") or raw_data.get("direct_phone"),
            "location_state": raw_data.get("state"),
            "priority_level": self._determine_priority(title),
            "source": "seamless"
        }
