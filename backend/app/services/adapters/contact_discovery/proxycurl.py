"""Proxycurl contact discovery adapter — LinkedIn profile scraper.

Proxycurl provides rich LinkedIn profile data without needing LinkedIn API access.
Best used when LinkedIn URLs are known. Sign up at https://nubela.co/proxycurl/.

Pricing: Free: 10 credits (one-time) | Paid: $0.01/call (pay-per-use)
"""
from typing import List, Dict, Any, Optional
import httpx
from app.services.adapters.base import ContactDiscoveryAdapter
from app.core.config import settings
from app.db.models.contact import PriorityLevel


class ProxycurlAdapter(ContactDiscoveryAdapter):
    """Adapter for Proxycurl LinkedIn profile enrichment API."""

    BASE_URL = "https://nubela.co/proxycurl/api/v2"

    def __init__(self, api_key: str = None):
        self.api_key = api_key or getattr(settings, 'PROXYCURL_API_KEY', None)

    def test_connection(self) -> bool:
        """Test connection to Proxycurl API."""
        if not self.api_key:
            return False
        try:
            with httpx.Client() as client:
                response = client.get(
                    f"{self.BASE_URL}/linkedin/company/employees/count/",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    params={"url": "https://www.linkedin.com/company/google/"},
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
        """Search for contacts using Proxycurl role lookup API."""
        if not self.api_key:
            raise ValueError("Proxycurl API key not configured")

        try:
            with httpx.Client() as client:
                # Use company role-based search
                params = {
                    "company_name": company_name,
                    "page_size": str(limit),
                    "enrich_profiles": "enrich",
                }
                if titles:
                    params["role"] = titles[0]
                else:
                    params["role"] = "HR Manager"
                if state:
                    params["country"] = "US"

                response = client.get(
                    f"{self.BASE_URL}/linkedin/company/role/",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    params=params,
                    timeout=30,
                )

                if response.status_code == 404:
                    return []  # Company not found
                response.raise_for_status()
                data = response.json()

                # Single profile result from role lookup
                if isinstance(data, dict) and data.get("profile"):
                    profile = data["profile"]
                    contact = self.normalize(profile)
                    if contact:
                        return [contact]
                    return []

                # Multiple results from search
                profiles = data if isinstance(data, list) else data.get("results", [])
                contacts = []
                for profile_info in profiles:
                    profile = profile_info if isinstance(profile_info, dict) else {}
                    if profile.get("profile"):
                        profile = profile["profile"]
                    contact = self.normalize(profile)
                    if contact:
                        contacts.append(contact)

                return contacts[:limit]

        except Exception as e:
            raise RuntimeError(f"Proxycurl API error: {str(e)}")

    def normalize(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize Proxycurl LinkedIn profile to standard format."""
        if not raw_data:
            return None

        # Proxycurl may return personal_email or work_email
        email = raw_data.get("personal_email")
        if not email:
            emails = raw_data.get("personal_emails", []) or []
            if emails:
                email = emails[0]

        if not email:
            return None

        # Extract current title from experiences
        title = raw_data.get("headline", "") or ""
        experiences = raw_data.get("experiences", []) or []
        if experiences:
            current_exp = experiences[0]  # Most recent
            title = current_exp.get("title", title) or title

        # Extract state from location
        location = raw_data.get("city", "") or ""
        state_str = raw_data.get("state", "") or ""
        state = state_str[:2].upper() if len(state_str) >= 2 else None

        # Phone
        phone_numbers = raw_data.get("phone_numbers", []) or []
        phone = phone_numbers[0] if phone_numbers else None

        first_name = raw_data.get("first_name", "") or ""
        last_name = raw_data.get("last_name", "") or ""

        # Fallback: split full_name
        if not first_name and raw_data.get("full_name"):
            parts = raw_data["full_name"].split(" ", 1)
            first_name = parts[0]
            last_name = parts[1] if len(parts) > 1 else ""

        return {
            "first_name": first_name,
            "last_name": last_name,
            "title": title,
            "email": email,
            "phone": phone,
            "location_state": state,
            "priority_level": self._determine_priority(title),
            "source": "proxycurl",
        }
