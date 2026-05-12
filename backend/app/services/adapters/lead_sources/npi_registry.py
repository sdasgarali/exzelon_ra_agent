"""NPI Registry lead source adapter for RCM LOB.

Fetches healthcare provider/practice data from the NPPES NPI Registry
(National Plan and Provider Enumeration System). Free API, no key required.

API docs: https://npiregistry.cms.hhs.gov/api-page
"""
import structlog
import requests
from typing import List, Dict, Any, Optional

from app.services.adapters.base import LeadSourceAdapter, RateLimitError

logger = structlog.get_logger()

BASE_URL = "https://npiregistry.cms.hhs.gov/api/"


class NPIRegistryAdapter(LeadSourceAdapter):
    """Adapter for NPPES NPI Registry (free, no API key needed).

    Fetches healthcare practices by taxonomy (specialty), state, and city.
    Useful for RCM LOB to find medical practices needing billing services.
    """

    def __init__(self):
        self._api_calls = 0

    def test_connection(self) -> bool:
        try:
            resp = requests.get(
                BASE_URL,
                params={"version": "2.1", "limit": 1, "state": "CA", "enumeration_type": "NPI-2"},
                timeout=10,
            )
            self._api_calls += 1
            return resp.status_code == 200
        except Exception:
            return False

    def fetch_leads(
        self,
        query: str = "",
        location: str = "United States",
        limit: int = 100,
        taxonomy: str = "",
        state: str = "",
        city: str = "",
        **kwargs,
    ) -> List[Dict[str, Any]]:
        """Fetch healthcare practices from NPI Registry.

        Args:
            query: Organization name search
            taxonomy: NUCC taxonomy description (e.g., "Internal Medicine")
            state: 2-letter state code
            city: City name
            limit: Max results (API caps at 200 per request)
        """
        leads = []
        api_limit = min(limit, 200)  # API max is 200 per call

        params = {
            "version": "2.1",
            "enumeration_type": "NPI-2",  # Organizations only
            "limit": api_limit,
        }

        if query:
            params["organization_name"] = query
        if taxonomy:
            params["taxonomy_description"] = taxonomy
        if state:
            params["state"] = state
        elif location and location != "United States":
            params["state"] = location

        if city:
            params["city"] = city

        try:
            resp = requests.get(BASE_URL, params=params, timeout=30)
            self._api_calls += 1
            resp.raise_for_status()
            data = resp.json()
        except requests.exceptions.HTTPError as e:
            if resp.status_code == 429:
                raise RateLimitError(f"NPI Registry rate limit: {e}", partial_results=leads)
            raise
        except Exception as e:
            logger.error("npi_registry_fetch_error", error=str(e))
            return leads

        results = data.get("results") or []
        for record in results:
            normalized = self.normalize(record)
            if normalized:
                leads.append(normalized)

        logger.info("npi_registry_fetched", count=len(leads), taxonomy=taxonomy, state=state)
        return leads

    def normalize(self, raw_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Normalize NPI record to standard lead format."""
        try:
            # Organization name
            basic = raw_data.get("basic", {})
            org_name = basic.get("organization_name", "")
            if not org_name:
                return None

            npi_number = str(raw_data.get("number", ""))

            # Primary practice address
            addresses = raw_data.get("addresses", [])
            practice_addr = None
            for addr in addresses:
                if addr.get("address_purpose") == "LOCATION":
                    practice_addr = addr
                    break
            if not practice_addr and addresses:
                practice_addr = addresses[0]

            state = (practice_addr or {}).get("state", "")
            city = (practice_addr or {}).get("city", "")
            address_1 = (practice_addr or {}).get("address_1", "")
            postal_code = (practice_addr or {}).get("postal_code", "")
            phone = (practice_addr or {}).get("telephone_number", "")

            # Taxonomy / specialty
            taxonomies = raw_data.get("taxonomies", [])
            primary_taxonomy = ""
            all_specialties = []
            for t in taxonomies:
                desc = t.get("desc", "")
                if desc:
                    all_specialties.append(desc)
                if t.get("primary", False) and desc:
                    primary_taxonomy = desc

            if not primary_taxonomy and all_specialties:
                primary_taxonomy = all_specialties[0]

            # Authorized official (potential contact)
            auth_official = basic.get("authorized_official_first_name", "")
            auth_official_last = basic.get("authorized_official_last_name", "")
            auth_official_title = basic.get("authorized_official_title_or_position", "")

            return {
                "client_name": org_name,
                "industry": "Healthcare",
                "state": state,
                "city": city,
                "domain": "",
                "source": "npi_registry",
                "source_url": f"https://npiregistry.cms.hhs.gov/provider-view/{npi_number}",
                "job_title": primary_taxonomy or "Healthcare Practice",
                "job_link": f"https://npiregistry.cms.hhs.gov/provider-view/{npi_number}",
                "posting_date": None,
                "contact_first_name": auth_official or None,
                "contact_last_name": auth_official_last or None,
                "contact_title": auth_official_title or None,
                "contact_phone": phone or None,
                "metadata": {
                    "npi_number": npi_number,
                    "specialty": primary_taxonomy,
                    "all_specialties": all_specialties,
                    "address": address_1,
                    "postal_code": postal_code,
                    "phone": phone,
                    "provider_count": len(taxonomies),
                },
            }
        except Exception as e:
            logger.warning("npi_normalize_error", error=str(e))
            return None

    @property
    def source_name(self) -> str:
        return "npi_registry"
