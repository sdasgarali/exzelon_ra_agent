"""Clearbit (now HubSpot Breeze) company enrichment adapter.

Clearbit provides company data including size, industry, revenue, and tech stack.
Sign up at https://clearbit.com/ or use via HubSpot integration.

Pricing: Free (with HubSpot) | API: from $99/month standalone
"""
from typing import Dict, Any, Optional
import httpx
from app.services.adapters.base import CompanyEnrichmentAdapter
from app.core.config import settings


class ClearbitAdapter(CompanyEnrichmentAdapter):
    """Adapter for Clearbit company enrichment API."""

    BASE_URL = "https://company.clearbit.com/v2"

    def __init__(self, api_key: str = None):
        self.api_key = api_key or getattr(settings, 'CLEARBIT_API_KEY', None)

    def test_connection(self) -> bool:
        """Test connection to Clearbit API."""
        if not self.api_key:
            return False
        try:
            with httpx.Client() as client:
                response = client.get(
                    f"{self.BASE_URL}/companies/find",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    params={"domain": "google.com"},
                    timeout=15,
                )
                # 200 = found, 404 = not found but auth OK, 401/403 = bad key
                return response.status_code in (200, 404, 422)
        except Exception:
            return False

    def enrich_company(
        self,
        company_name: str,
        domain: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Enrich company data using Clearbit API."""
        if not self.api_key:
            raise ValueError(
                "Clearbit API key not configured. "
                "Get one at https://clearbit.com/"
            )

        try:
            with httpx.Client() as client:
                params = {}
                if domain:
                    params["domain"] = domain
                else:
                    params["name"] = company_name

                response = client.get(
                    f"{self.BASE_URL}/companies/find",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    params=params,
                    timeout=30,
                )

                if response.status_code == 404:
                    return {"company_name": company_name, "found": False}

                response.raise_for_status()
                data = response.json()
                return self.normalize(data)

        except Exception as e:
            raise RuntimeError(f"Clearbit API error: {str(e)}")

    def normalize(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize Clearbit company data to standard format."""
        if not raw_data:
            return None

        # Extract metrics
        metrics = raw_data.get("metrics", {}) or {}
        geo = raw_data.get("geo", {}) or {}

        # Tech stack
        tech = raw_data.get("tech", []) or []

        return {
            "company_name": raw_data.get("name", ""),
            "domain": raw_data.get("domain", ""),
            "industry": raw_data.get("industry", "") or raw_data.get("category", {}).get("industry", ""),
            "employee_count": metrics.get("employees") or metrics.get("employeesRange"),
            "revenue": metrics.get("estimatedAnnualRevenue"),
            "description": raw_data.get("description", ""),
            "address": f"{geo.get('streetNumber', '')} {geo.get('streetName', '')}, {geo.get('city', '')}, {geo.get('state', '')} {geo.get('postalCode', '')}".strip(", "),
            "country": geo.get("country", ""),
            "tech_stack": tech,
            "founded_year": raw_data.get("foundedYear"),
            "logo_url": raw_data.get("logo"),
            "linkedin_url": raw_data.get("linkedin", {}).get("handle", "") if isinstance(raw_data.get("linkedin"), dict) else "",
            "found": True,
            "raw_response": raw_data,
        }
