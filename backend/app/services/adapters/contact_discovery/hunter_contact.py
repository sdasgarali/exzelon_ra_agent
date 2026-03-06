"""Hunter.io contact finder adapter — domain-based email discovery.

Hunter.io finds professional email addresses using domain search and email finder.
Sign up at https://hunter.io/ to get an API key.

Pricing: Free: 25 requests/month | Paid: from $49/month
"""
from typing import List, Dict, Any, Optional
import httpx
from app.services.adapters.base import ContactDiscoveryAdapter
from app.core.config import settings
from app.db.models.contact import PriorityLevel


class HunterContactAdapter(ContactDiscoveryAdapter):
    """Adapter for Hunter.io contact discovery (Domain Search + Email Finder)."""

    BASE_URL = "https://api.hunter.io/v2"

    def __init__(self, api_key: str = None):
        self.api_key = api_key or getattr(settings, 'HUNTER_API_KEY', None)

    def test_connection(self) -> bool:
        """Test connection to Hunter.io API."""
        if not self.api_key:
            return False
        try:
            with httpx.Client() as client:
                response = client.get(
                    f"{self.BASE_URL}/account",
                    params={"api_key": self.api_key},
                    timeout=15,
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
        if any(kw in title_lower for kw in ["hr manager", "hrbp", "hr director", "vp hr", "vp human"]):
            return PriorityLevel.P3_HR_MANAGER
        if any(kw in title_lower for kw in ["operations", "plant manager", "production", "business leader"]):
            return PriorityLevel.P4_OPS_LEADER
        return PriorityLevel.P5_FUNCTIONAL_MANAGER

    def search_contacts(
        self,
        company_name: str,
        job_title: Optional[str] = None,
        state: Optional[str] = None,
        titles: Optional[List[str]] = None,
        limit: int = 4,
    ) -> List[Dict[str, Any]]:
        """Search for contacts using Hunter.io domain search."""
        if not self.api_key:
            raise ValueError("Hunter.io API key not configured")

        try:
            with httpx.Client() as client:
                # Domain search — finds emails at a domain
                params = {
                    "api_key": self.api_key,
                    "company": company_name,
                    "limit": limit * 2,
                }
                if titles:
                    params["seniority"] = "senior,executive"

                response = client.get(
                    f"{self.BASE_URL}/domain-search",
                    params=params,
                    timeout=30,
                )
                response.raise_for_status()
                data = response.json()

                emails_data = data.get("data", {}).get("emails", [])
                if not emails_data:
                    return []

                contacts = []
                for email_info in emails_data:
                    contact = self.normalize(email_info)
                    if contact:
                        contacts.append(contact)

                return contacts[:limit]

        except Exception as e:
            raise RuntimeError(f"Hunter.io API error: {str(e)}")

    def normalize(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize Hunter.io email result to standard format."""
        if not raw_data:
            return None

        email = raw_data.get("value")
        if not email:
            return None

        title = raw_data.get("position", "") or ""
        phone = raw_data.get("phone_number")

        return {
            "first_name": raw_data.get("first_name", "") or "",
            "last_name": raw_data.get("last_name", "") or "",
            "title": title,
            "email": email,
            "phone": phone,
            "location_state": None,
            "priority_level": self._determine_priority(title),
            "source": "hunter_contact",
        }
