"""People Data Labs (PDL) contact discovery adapter — massive person database (3B+ profiles).

PDL offers SQL-like query DSL for finding professionals across a huge dataset.
Sign up at https://www.peopledatalabs.com/ to get an API key.

Pricing: Free: 100 requests/month | Paid: $0.01/match (pay-per-use)
"""
from typing import List, Dict, Any, Optional
import httpx
from app.services.adapters.base import ContactDiscoveryAdapter
from app.core.config import settings
from app.db.models.contact import PriorityLevel


class PDLAdapter(ContactDiscoveryAdapter):
    """Adapter for People Data Labs person search API."""

    BASE_URL = "https://api.peopledatalabs.com/v5"

    def __init__(self, api_key: str = None):
        self.api_key = api_key or getattr(settings, 'PDL_API_KEY', None)

    def test_connection(self) -> bool:
        """Test connection to People Data Labs API."""
        if not self.api_key:
            return False
        try:
            with httpx.Client() as client:
                response = client.get(
                    f"{self.BASE_URL}/person/search",
                    headers={"X-Api-Key": self.api_key},
                    params={
                        "query": "SELECT * FROM person WHERE job_company_name='test' LIMIT 1",
                        "size": 1,
                    },
                    timeout=15,
                )
                # PDL returns 200 even for empty results; 401/403 for bad key
                return response.status_code in (200, 400)  # 400 = valid key but bad query
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
        """Search for contacts using PDL person search with SQL-like DSL."""
        if not self.api_key:
            raise ValueError("People Data Labs API key not configured")

        try:
            with httpx.Client() as client:
                # Build Elasticsearch-style query
                must_clauses = [
                    {"match": {"job_company_name": company_name}},
                ]

                if titles:
                    must_clauses.append({
                        "bool": {
                            "should": [{"match": {"job_title": t}} for t in titles],
                            "minimum_should_match": 1,
                        }
                    })
                else:
                    must_clauses.append({
                        "bool": {
                            "should": [
                                {"match": {"job_title": "HR Manager"}},
                                {"match": {"job_title": "HR Director"}},
                                {"match": {"job_title": "Recruiter"}},
                                {"match": {"job_title": "Operations Manager"}},
                                {"match": {"job_title": "Talent Acquisition"}},
                            ],
                            "minimum_should_match": 1,
                        }
                    })

                if state:
                    must_clauses.append({"match": {"location_region": state}})

                query = {
                    "bool": {
                        "must": must_clauses,
                    }
                }

                response = client.get(
                    f"{self.BASE_URL}/person/search",
                    headers={
                        "X-Api-Key": self.api_key,
                        "Content-Type": "application/json",
                    },
                    params={
                        "query": str(query).replace("'", '"'),
                        "size": limit * 2,
                    },
                    timeout=30,
                )
                response.raise_for_status()
                data = response.json()

                results = data.get("data", [])
                contacts = []
                for person in results:
                    contact = self.normalize(person)
                    if contact:
                        contacts.append(contact)

                return contacts[:limit]

        except Exception as e:
            raise RuntimeError(f"People Data Labs API error: {str(e)}")

    def normalize(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize PDL person data to standard format."""
        if not raw_data:
            return None

        # PDL returns work_email or personal emails
        email = raw_data.get("work_email")
        if not email:
            emails = raw_data.get("emails", [])
            if emails:
                # Prefer work emails
                for e in emails:
                    if isinstance(e, dict):
                        if e.get("type") == "current_professional":
                            email = e.get("address")
                            break
                if not email:
                    for e in emails:
                        if isinstance(e, dict):
                            email = e.get("address")
                            break
                        elif isinstance(e, str):
                            email = e
                            break

        if not email:
            return None

        title = raw_data.get("job_title", "") or ""

        # Phone
        phones = raw_data.get("phone_numbers", []) or raw_data.get("mobile_phone", None)
        phone = None
        if isinstance(phones, list) and phones:
            phone = phones[0] if isinstance(phones[0], str) else phones[0].get("number")
        elif isinstance(phones, str):
            phone = phones

        return {
            "first_name": raw_data.get("first_name", "") or "",
            "last_name": raw_data.get("last_name", "") or "",
            "title": title,
            "email": email,
            "phone": phone,
            "location_state": raw_data.get("location_region"),
            "priority_level": self._determine_priority(title),
            "source": "pdl",
        }
