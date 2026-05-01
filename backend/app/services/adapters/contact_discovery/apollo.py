"""Apollo.io contact discovery adapter."""
from typing import List, Dict, Any, Optional
import httpx
import structlog
from app.services.adapters.base import ContactDiscoveryAdapter, CreditsExhaustedError
from app.core.config import settings
from app.db.models.contact import PriorityLevel

logger = structlog.get_logger()


class ApolloCreditsExhaustedError(CreditsExhaustedError):
    """Raised when Apollo API credits are exhausted."""

    def __init__(self, message: str = "Apollo credits exhausted"):
        super().__init__(message, adapter_name="apollo")


class ApolloAdapter(ContactDiscoveryAdapter):
    """Adapter for Apollo.io contact discovery API (Search + Enrich)."""

    BASE_URL = "https://api.apollo.io/api/v1"

    def __init__(self, api_key: str = None):
        self.api_key = api_key or settings.APOLLO_API_KEY
        self._credits_exhausted = False

    def test_connection(self) -> bool:
        """Test connection to Apollo API."""
        if not self.api_key:
            return False
        try:
            with httpx.Client() as client:
                # Use search endpoint as health check (free, no credits)
                response = client.post(
                    f"{self.BASE_URL}/mixed_people/api_search",
                    params={"per_page": 1, "person_titles[]": ["CEO"]},
                    headers={"X-Api-Key": self.api_key, "Accept": "application/json"},
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
        if any(kw in title_lower for kw in ["hr manager", "hrbp", "hr director", "vp hr", "vp human"]):
            return PriorityLevel.P3_HR_MANAGER
        if any(kw in title_lower for kw in ["operations", "plant manager", "production", "business leader"]):
            return PriorityLevel.P4_OPS_LEADER
        return PriorityLevel.P5_FUNCTIONAL_MANAGER

    def _search_people(self, client, company_name, titles, state, limit, domain=None):
        """Step 1: Search for people IDs (free, no credits consumed).

        Prefers domain-based search (precise) over company name (fuzzy).
        e.g. domain="cognizant.com" matches all Cognizant employees regardless
        of whether the company is stored as "Cognizant", "Cognizant Technologies", or "CTS".
        """
        params = {
            "per_page": limit * 2,
        }
        # Prefer domain search (precise) over company name (fuzzy)
        if domain:
            params["q_organization_domains"] = domain
        else:
            params["q_organization_name"] = company_name
        # Only apply title filter when explicitly passed by caller
        if titles:
            params["person_titles[]"] = titles

        response = client.post(
            f"{self.BASE_URL}/mixed_people/api_search",
            params=params,
            headers={
                "Content-Type": "application/json",
                "X-Api-Key": self.api_key,
                "Accept": "application/json"
            },
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        people = data.get("people", [])
        # Filter to those with email available
        return [p for p in people if p.get("has_email")][:limit]

    def _enrich_person(self, client, person_id):
        """Step 2: Enrich a person to get email/details (costs credits)."""
        if self._credits_exhausted:
            raise ApolloCreditsExhaustedError("Apollo credits exhausted")

        response = client.post(
            f"{self.BASE_URL}/people/match",
            params={
                "id": person_id,
                "reveal_personal_emails": "true"
            },
            headers={
                "Content-Type": "application/json",
                "X-Api-Key": self.api_key,
                "Accept": "application/json"
            },
            timeout=30
        )

        # Detect credit exhaustion
        if response.status_code == 422:
            error_data = response.json()
            error_msg = error_data.get("error", "")
            if "insufficient credits" in error_msg.lower():
                self._credits_exhausted = True
                logger.error("Apollo API credits exhausted! Upgrade plan at https://app.apollo.io/#/settings/plans/upgrade")
                raise ApolloCreditsExhaustedError(error_msg)

        response.raise_for_status()
        data = response.json()
        return data.get("person")

    def search_contacts(
        self,
        company_name: str,
        job_title: Optional[str] = None,
        state: Optional[str] = None,
        titles: Optional[List[str]] = None,
        limit: int = 4,
        domain: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Search for contacts at a company using Apollo API (Search + Enrich).

        Prefers domain-based search when available for precise company matching.
        Falls back to company name search otherwise.
        """
        if not self.api_key:
            raise ValueError("Apollo API key not configured")

        if self._credits_exhausted:
            raise ApolloCreditsExhaustedError("Apollo credits exhausted - skipping")

        try:
            with httpx.Client() as client:
                # Step 1: Search for people IDs (free)
                people = self._search_people(client, company_name, titles, state, limit, domain=domain)
                search_key = domain or company_name
                logger.info(f"Apollo search found {len(people)} candidates for {search_key}")

                if not people:
                    return []

                # Step 2: Enrich each person to get emails (costs credits)
                contacts = []
                for person_preview in people:
                    try:
                        person = self._enrich_person(client, person_preview["id"])
                        if person:
                            contact = self.normalize(person)
                            if contact:
                                contacts.append(contact)
                    except ApolloCreditsExhaustedError:
                        logger.error("Apollo credits exhausted - stopping enrichment")
                        raise
                    except Exception as e:
                        logger.warning(f"Apollo enrich failed for {person_preview.get('first_name', '?')}: {e}")

                return contacts[:limit]

        except ApolloCreditsExhaustedError:
            raise
        except Exception as e:
            raise RuntimeError(f"Apollo API error: {str(e)}")

    def normalize(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize Apollo API response to standard format."""
        if not raw_data:
            return None

        email = raw_data.get("email")
        if not email:
            return None

        title = raw_data.get("title") or ""
        phone = None
        phone_numbers = raw_data.get("phone_numbers", [])
        if phone_numbers and len(phone_numbers) > 0:
            phone = phone_numbers[0].get("sanitized_number", phone_numbers[0].get("number"))

        return {
            "first_name": raw_data.get("first_name", ""),
            "last_name": raw_data.get("last_name", ""),
            "title": title,
            "email": email,
            "phone": phone,
            "location_state": raw_data.get("state"),
            "priority_level": self._determine_priority(title),
            "source": "apollo"
        }

