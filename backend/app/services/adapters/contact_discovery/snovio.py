"""Snov.io contact discovery adapter — email finder with OAuth authentication.

Snov.io provides email finding and verification with a credit-based system.
Sign up at https://snov.io/ to get client credentials.

Pricing: Free: 50 credits/month | Paid: from $39/month
"""
from typing import List, Dict, Any, Optional
import httpx
from app.services.adapters.base import ContactDiscoveryAdapter
from app.core.config import settings
from app.db.models.contact import PriorityLevel


class SnovioAdapter(ContactDiscoveryAdapter):
    """Adapter for Snov.io contact discovery API (OAuth + Domain Search)."""

    BASE_URL = "https://api.snov.io"

    def __init__(self, client_id: str = None, client_secret: str = None, api_key: str = None):
        self.client_id = client_id or getattr(settings, 'SNOVIO_CLIENT_ID', None)
        self.client_secret = client_secret or getattr(settings, 'SNOVIO_CLIENT_SECRET', None)
        self._access_token = None

    def _get_access_token(self) -> str:
        """Get OAuth access token using client credentials."""
        if self._access_token:
            return self._access_token

        if not self.client_id or not self.client_secret:
            raise ValueError("Snov.io client_id and client_secret required")

        with httpx.Client() as client:
            response = client.post(
                f"{self.BASE_URL}/v1/oauth/access_token",
                json={
                    "grant_type": "client_credentials",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                },
                timeout=15,
            )
            response.raise_for_status()
            data = response.json()
            self._access_token = data.get("access_token")
            return self._access_token

    def test_connection(self) -> bool:
        """Test connection to Snov.io API."""
        if not self.client_id or not self.client_secret:
            return False
        try:
            token = self._get_access_token()
            return bool(token)
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
        """Search for contacts using Snov.io domain email search."""
        if not self.client_id or not self.client_secret:
            raise ValueError("Snov.io credentials not configured")

        try:
            token = self._get_access_token()

            with httpx.Client() as client:
                # Get domain emails with contact info
                params = {
                    "access_token": token,
                    "domain": company_name.lower().replace(" ", "").replace(",", "") + ".com",
                    "type": "all",
                    "limit": limit * 2,
                }

                response = client.get(
                    f"{self.BASE_URL}/v2/domain-emails-with-info",
                    params=params,
                    timeout=30,
                )
                response.raise_for_status()
                data = response.json()

                emails_data = data.get("emails", [])
                if not emails_data:
                    # Try company name search as fallback
                    response = client.post(
                        f"{self.BASE_URL}/v1/get-emails-from-names",
                        json={
                            "access_token": token,
                            "firstName": "",
                            "lastName": "",
                            "domain": company_name,
                        },
                        timeout=30,
                    )
                    if response.status_code == 200:
                        data = response.json()
                        emails_data = data.get("data", {}).get("emails", [])

                contacts = []
                for email_info in emails_data:
                    contact = self.normalize(email_info)
                    if contact:
                        contacts.append(contact)

                return contacts[:limit]

        except Exception as e:
            raise RuntimeError(f"Snov.io API error: {str(e)}")

    def normalize(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize Snov.io email result to standard format."""
        if not raw_data:
            return None

        email = raw_data.get("email")
        if not email:
            return None

        first_name = raw_data.get("firstName", "") or raw_data.get("first_name", "") or ""
        last_name = raw_data.get("lastName", "") or raw_data.get("last_name", "") or ""
        title = raw_data.get("position", "") or raw_data.get("sourcePage", "") or ""

        return {
            "first_name": first_name,
            "last_name": last_name,
            "title": title,
            "email": email,
            "phone": None,
            "location_state": None,
            "priority_level": self._determine_priority(title),
            "source": "snovio",
        }
