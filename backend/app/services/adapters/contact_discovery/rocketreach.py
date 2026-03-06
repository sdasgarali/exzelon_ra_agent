"""RocketReach contact discovery adapter — best for executive/decision-maker contacts.

RocketReach provides professional contact info with strong executive coverage.
Sign up at https://rocketreach.co/ to get an API key.

Pricing: Free: 5 lookups/month | Paid: from $99/month
"""
from typing import List, Dict, Any, Optional
import httpx
from app.services.adapters.base import ContactDiscoveryAdapter
from app.core.config import settings
from app.db.models.contact import PriorityLevel


class RocketReachAdapter(ContactDiscoveryAdapter):
    """Adapter for RocketReach contact lookup API."""

    BASE_URL = "https://api.rocketreach.co/api/v2"

    def __init__(self, api_key: str = None):
        self.api_key = api_key or getattr(settings, 'ROCKETREACH_API_KEY', None)

    def test_connection(self) -> bool:
        """Test connection to RocketReach API."""
        if not self.api_key:
            return False
        try:
            with httpx.Client() as client:
                response = client.get(
                    f"{self.BASE_URL}/account",
                    headers={"Api-Key": self.api_key},
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
        """Search for contacts using RocketReach person search."""
        if not self.api_key:
            raise ValueError("RocketReach API key not configured")

        try:
            with httpx.Client() as client:
                # Person search by company
                query = {
                    "current_employer": [company_name],
                    "page_size": limit * 2,
                }
                if titles:
                    query["current_title"] = titles
                else:
                    query["current_title"] = [
                        "HR Manager", "HR Director", "Talent Acquisition",
                        "Recruiter", "Operations Manager", "HRBP",
                    ]
                if state:
                    query["location"] = [f"{state}, US"]

                response = client.post(
                    f"{self.BASE_URL}/search",
                    headers={
                        "Api-Key": self.api_key,
                        "Content-Type": "application/json",
                    },
                    json={"query": query},
                    timeout=30,
                )
                response.raise_for_status()
                data = response.json()

                profiles = data.get("profiles", [])
                if not profiles:
                    return []

                # Lookup each profile to get email
                contacts = []
                for profile in profiles[:limit]:
                    try:
                        lookup_response = client.get(
                            f"{self.BASE_URL}/lookupProfile",
                            headers={"Api-Key": self.api_key},
                            params={"id": profile.get("id")},
                            timeout=30,
                        )
                        if lookup_response.status_code == 200:
                            person = lookup_response.json()
                            contact = self.normalize(person)
                            if contact:
                                contacts.append(contact)
                    except Exception:
                        continue

                return contacts[:limit]

        except Exception as e:
            raise RuntimeError(f"RocketReach API error: {str(e)}")

    def normalize(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize RocketReach person data to standard format."""
        if not raw_data:
            return None

        # Get email — RocketReach returns emails in various fields
        email = None
        if raw_data.get("current_work_email"):
            email = raw_data["current_work_email"]
        elif raw_data.get("emails") and len(raw_data["emails"]) > 0:
            email = raw_data["emails"][0]
        elif raw_data.get("professional_email"):
            email = raw_data["professional_email"]

        if not email:
            return None

        title = raw_data.get("current_title", "") or ""

        # Extract state from location
        location = raw_data.get("location", "") or ""
        state = None
        if location:
            parts = [p.strip() for p in location.split(",")]
            for part in parts:
                if len(part) == 2 and part.isalpha():
                    state = part.upper()
                    break

        # Phone
        phones = raw_data.get("phones", []) or []
        phone = phones[0].get("number") if phones else None

        return {
            "first_name": raw_data.get("first_name", "") or "",
            "last_name": raw_data.get("last_name", "") or "",
            "title": title,
            "email": email,
            "phone": phone,
            "location_state": state,
            "priority_level": self._determine_priority(title),
            "source": "rocketreach",
        }
