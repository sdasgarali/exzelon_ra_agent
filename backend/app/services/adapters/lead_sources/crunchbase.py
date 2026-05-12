"""Crunchbase lead source adapter for Software Dev & AI Services LOBs.

Fetches company data from Crunchbase — funding rounds, employee count,
tech categories, and growth indicators. Ideal for finding companies
that need software development or AI services.

Requires: CRUNCHBASE_API_KEY
"""
import structlog
import requests
from typing import List, Dict, Any, Optional
from datetime import datetime

from app.services.adapters.base import LeadSourceAdapter, RateLimitError

logger = structlog.get_logger()

BASE_URL = "https://api.crunchbase.com/api/v4"


class CrunchbaseAdapter(LeadSourceAdapter):
    """Adapter for Crunchbase API.

    Searches for companies by category, location, funding stage, and size.
    Returns company profile, funding info, and growth signals useful for
    targeting software dev and AI services prospects.
    """

    def __init__(self, api_key: str = ""):
        self.api_key = api_key
        self._api_calls = 0

    def test_connection(self) -> bool:
        if not self.api_key:
            return False
        try:
            resp = requests.get(
                f"{BASE_URL}/autocompletes",
                params={"user_key": self.api_key, "query": "test", "limit": 1},
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
        limit: int = 25,
        categories: Optional[List[str]] = None,
        funding_stage: str = "",
        min_employees: int = 0,
        max_employees: int = 0,
        **kwargs,
    ) -> List[Dict[str, Any]]:
        """Fetch companies from Crunchbase.

        Args:
            query: Company name or keyword search
            categories: Crunchbase category groups (e.g., ["software", "artificial-intelligence"])
            funding_stage: Funding stage filter (e.g., "seed", "series_a", "series_b")
            min_employees: Minimum employee count
            max_employees: Maximum employee count
            limit: Max results
        """
        if not self.api_key:
            logger.warning("crunchbase_no_key")
            return []

        leads = []

        # Build search query using Organization Search endpoint
        field_ids = [
            "identifier", "short_description", "location_identifiers",
            "categories", "num_employees_enum", "funding_total",
            "last_funding_type", "founded_on", "website_url",
            "linkedin", "company_type", "operating_status",
        ]

        query_params = []

        if categories:
            query_params.append({
                "type": "predicate",
                "field_id": "categories",
                "operator_id": "includes",
                "values": categories,
            })

        if funding_stage:
            query_params.append({
                "type": "predicate",
                "field_id": "last_funding_type",
                "operator_id": "eq",
                "values": [funding_stage],
            })

        if min_employees:
            query_params.append({
                "type": "predicate",
                "field_id": "num_employees_enum",
                "operator_id": "gte",
                "values": [_employee_enum(min_employees)],
            })

        # Only active companies
        query_params.append({
            "type": "predicate",
            "field_id": "operating_status",
            "operator_id": "eq",
            "values": ["active"],
        })

        body = {
            "field_ids": field_ids,
            "query": query_params,
            "order": [{"field_id": "rank_org", "sort": "asc"}],
            "limit": min(limit, 25),
        }

        try:
            resp = requests.post(
                f"{BASE_URL}/searches/organizations",
                params={"user_key": self.api_key},
                json=body,
                timeout=30,
            )
            self._api_calls += 1

            if resp.status_code == 429:
                raise RateLimitError("Crunchbase rate limit", partial_results=leads)
            resp.raise_for_status()
            data = resp.json()
        except RateLimitError:
            raise
        except Exception as e:
            logger.error("crunchbase_fetch_error", error=str(e))
            return leads

        entities = data.get("entities") or []
        for entity in entities:
            normalized = self.normalize(entity)
            if normalized:
                leads.append(normalized)

        logger.info("crunchbase_fetched", count=len(leads), categories=categories)
        return leads

    def normalize(self, raw_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Normalize Crunchbase entity to standard lead format."""
        try:
            props = raw_data.get("properties", {})
            identifier = props.get("identifier", {})
            name = identifier.get("value", "")
            permalink = identifier.get("permalink", "")
            if not name:
                return None

            description = props.get("short_description", "")
            website = props.get("website_url", "")
            linkedin = props.get("linkedin", {})
            linkedin_url = linkedin.get("value", "") if isinstance(linkedin, dict) else ""

            # Location
            locations = props.get("location_identifiers", [])
            state = ""
            city = ""
            for loc in locations:
                loc_type = loc.get("location_type", "")
                if loc_type == "region":
                    state = loc.get("value", "")
                elif loc_type == "city":
                    city = loc.get("value", "")

            # Categories
            categories = props.get("categories", [])
            cat_names = [c.get("value", "") for c in categories if isinstance(c, dict)]

            # Funding
            funding_total = props.get("funding_total", {})
            funding_amount = funding_total.get("value_usd", 0) if isinstance(funding_total, dict) else 0
            last_funding_type = props.get("last_funding_type", "")

            # Employees
            num_employees = props.get("num_employees_enum", "")

            # Founded
            founded_on = props.get("founded_on", "")

            # Domain from website
            domain = ""
            if website:
                from urllib.parse import urlparse
                parsed = urlparse(website)
                domain = parsed.netloc.replace("www.", "")

            # Determine industry
            industry = _infer_industry(cat_names)

            return {
                "client_name": name,
                "industry": industry,
                "state": state,
                "city": city,
                "domain": domain,
                "source": "crunchbase",
                "source_url": f"https://www.crunchbase.com/organization/{permalink}",
                "job_title": industry or "Technology Company",
                "job_link": f"https://www.crunchbase.com/organization/{permalink}",
                "posting_date": None,
                "employer_website": website,
                "employer_linkedin_url": linkedin_url,
                "company_size": num_employees,
                "metadata": {
                    "description": description,
                    "categories": cat_names[:5],
                    "funding_total_usd": funding_amount,
                    "last_funding_type": last_funding_type,
                    "num_employees": num_employees,
                    "founded_on": founded_on,
                    "tech_stack": [],
                },
            }
        except Exception as e:
            logger.warning("crunchbase_normalize_error", error=str(e))
            return None

    @property
    def source_name(self) -> str:
        return "crunchbase"


def _employee_enum(count: int) -> str:
    """Convert employee count to Crunchbase enum."""
    if count <= 10:
        return "c_00001_00010"
    if count <= 50:
        return "c_00011_00050"
    if count <= 100:
        return "c_00051_00100"
    if count <= 250:
        return "c_00101_00250"
    if count <= 500:
        return "c_00251_00500"
    if count <= 1000:
        return "c_00501_01000"
    return "c_01001_05000"


def _infer_industry(categories: List[str]) -> str:
    """Infer industry from Crunchbase categories."""
    cats_lower = {c.lower() for c in categories}
    if cats_lower & {"artificial intelligence", "machine learning", "deep learning", "natural language processing"}:
        return "AI & Machine Learning"
    if cats_lower & {"software", "saas", "enterprise software", "developer tools"}:
        return "Software"
    if cats_lower & {"health care", "medical", "biotechnology", "pharmaceutical"}:
        return "Healthcare"
    if cats_lower & {"financial services", "fintech", "banking", "insurance"}:
        return "Financial Services"
    if cats_lower & {"e-commerce", "retail", "marketplace"}:
        return "Retail"
    if cats_lower & {"edtech", "education"}:
        return "Education"
    if cats_lower & {"marketing", "advertising", "analytics"}:
        return "Marketing & Advertising"
    return "Technology"
