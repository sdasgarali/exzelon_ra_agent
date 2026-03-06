"""OpenCorporates company enrichment adapter — corporate registry data.

OpenCorporates provides official company registration data from government filings.
Sign up at https://opencorporates.com/ for API access.

Pricing: Free: 500 requests/month | Paid: custom pricing
"""
from typing import Dict, Any, Optional
import httpx
from app.services.adapters.base import CompanyEnrichmentAdapter
from app.core.config import settings


class OpenCorporatesAdapter(CompanyEnrichmentAdapter):
    """Adapter for OpenCorporates company search API."""

    BASE_URL = "https://api.opencorporates.com/v0.4"

    def __init__(self, api_key: str = None):
        self.api_key = api_key or getattr(settings, 'OPENCORPORATES_API_KEY', None)

    def test_connection(self) -> bool:
        """Test connection to OpenCorporates API."""
        if not self.api_key:
            return False
        try:
            with httpx.Client() as client:
                response = client.get(
                    f"{self.BASE_URL}/companies/search",
                    params={
                        "q": "Google",
                        "api_token": self.api_key,
                        "per_page": 1,
                    },
                    timeout=15,
                )
                return response.status_code == 200
        except Exception:
            return False

    def enrich_company(
        self,
        company_name: str,
        domain: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Enrich company with OpenCorporates registration data."""
        if not self.api_key:
            raise ValueError(
                "OpenCorporates API key not configured. "
                "Get one at https://opencorporates.com/"
            )

        try:
            with httpx.Client() as client:
                # Search for company
                params = {
                    "q": company_name,
                    "api_token": self.api_key,
                    "per_page": 5,
                    "jurisdiction_code": "us",
                }

                response = client.get(
                    f"{self.BASE_URL}/companies/search",
                    params=params,
                    timeout=30,
                )
                response.raise_for_status()
                data = response.json()

                companies = data.get("results", {}).get("companies", [])
                if not companies:
                    return {"company_name": company_name, "found": False}

                # Use the first (best match) result
                company_data = companies[0].get("company", {})

                # Try to get detailed info if we have a jurisdiction + number
                jurisdiction = company_data.get("jurisdiction_code", "")
                company_number = company_data.get("company_number", "")
                if jurisdiction and company_number:
                    try:
                        detail_response = client.get(
                            f"{self.BASE_URL}/companies/{jurisdiction}/{company_number}",
                            params={"api_token": self.api_key},
                            timeout=30,
                        )
                        if detail_response.status_code == 200:
                            detail_data = detail_response.json()
                            company_data = detail_data.get("results", {}).get("company", company_data)
                    except Exception:
                        pass  # Use search result data

                return self.normalize(company_data)

        except Exception as e:
            raise RuntimeError(f"OpenCorporates API error: {str(e)}")

    def normalize(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize OpenCorporates company data to standard format."""
        if not raw_data:
            return None

        # Address
        registered_address = raw_data.get("registered_address", {}) or {}
        address_str = raw_data.get("registered_address_in_full", "")
        if not address_str and registered_address:
            parts = [
                registered_address.get("street_address", ""),
                registered_address.get("locality", ""),
                registered_address.get("region", ""),
                registered_address.get("postal_code", ""),
            ]
            address_str = ", ".join(p for p in parts if p)

        # Extract officers if available
        officers = []
        for officer_data in raw_data.get("officers", []) or []:
            officer = officer_data.get("officer", {})
            if officer:
                officers.append({
                    "name": officer.get("name", ""),
                    "position": officer.get("position", ""),
                })

        # Incorporation date -> founded year
        incorporation_date = raw_data.get("incorporation_date", "")
        founded_year = None
        if incorporation_date:
            try:
                founded_year = int(incorporation_date[:4])
            except (ValueError, IndexError):
                pass

        return {
            "company_name": raw_data.get("name", ""),
            "domain": "",
            "industry": raw_data.get("industry_codes", [{}])[0].get("description", "") if raw_data.get("industry_codes") else "",
            "employee_count": None,
            "revenue": None,
            "description": raw_data.get("company_type", ""),
            "address": address_str,
            "country": raw_data.get("jurisdiction_code", "").upper()[:2] if raw_data.get("jurisdiction_code") else "",
            "tech_stack": [],
            "founded_year": founded_year,
            "incorporation_date": incorporation_date,
            "company_number": raw_data.get("company_number", ""),
            "status": raw_data.get("current_status", ""),
            "officers": officers[:5],
            "found": True,
            "raw_response": raw_data,
        }
