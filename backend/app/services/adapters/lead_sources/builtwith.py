"""BuiltWith lead source adapter for Software Dev & Digital Marketing LOBs.

Fetches technology profile data for websites — identifies tech stacks,
CMS platforms, analytics tools, and frameworks in use. Useful for finding
companies with outdated tech stacks that need modernization.

Requires: BUILTWITH_API_KEY
"""
import structlog
import requests
from typing import List, Dict, Any, Optional

from app.services.adapters.base import LeadSourceAdapter, RateLimitError

logger = structlog.get_logger()

BASE_URL = "https://api.builtwith.com"


class BuiltWithAdapter(LeadSourceAdapter):
    """Adapter for BuiltWith API.

    Looks up technology profiles for domains. Can search by technology
    to find companies using specific (often outdated) platforms.
    """

    def __init__(self, api_key: str = ""):
        self.api_key = api_key
        self._api_calls = 0

    def test_connection(self) -> bool:
        if not self.api_key:
            return False
        try:
            resp = requests.get(
                f"{BASE_URL}/v21/api.json",
                params={"KEY": self.api_key, "LOOKUP": "example.com"},
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
        limit: int = 50,
        technology: str = "",
        domains: Optional[List[str]] = None,
        **kwargs,
    ) -> List[Dict[str, Any]]:
        """Fetch tech profile data from BuiltWith.

        Two modes:
        1. Domain lookup: Pass `domains` list to get tech profiles
        2. Technology search: Pass `technology` to find sites using it

        Args:
            technology: Technology name to search for (e.g., "WordPress", "jQuery")
            domains: List of domains to look up
            limit: Max results
        """
        if not self.api_key:
            logger.warning("builtwith_no_key")
            return []

        leads = []

        if domains:
            # Mode 1: Look up specific domains
            for domain in domains[:limit]:
                result = self._lookup_domain(domain)
                if result:
                    leads.append(result)
        elif technology:
            # Mode 2: Search by technology
            leads = self._search_by_technology(technology, limit)
        else:
            logger.warning("builtwith_no_query", msg="Provide domains or technology param")
            return []

        logger.info("builtwith_fetched", count=len(leads), technology=technology)
        return leads

    def _lookup_domain(self, domain: str) -> Optional[Dict[str, Any]]:
        """Look up technology profile for a single domain."""
        try:
            resp = requests.get(
                f"{BASE_URL}/v21/api.json",
                params={"KEY": self.api_key, "LOOKUP": domain},
                timeout=30,
            )
            self._api_calls += 1

            if resp.status_code == 429:
                raise RateLimitError(f"BuiltWith rate limit for {domain}")
            resp.raise_for_status()
            data = resp.json()
        except RateLimitError:
            raise
        except Exception as e:
            logger.warning("builtwith_lookup_error", domain=domain, error=str(e))
            return None

        results = data.get("Results") or []
        if not results:
            return None

        return self.normalize({"domain": domain, "result": results[0]})

    def _search_by_technology(self, technology: str, limit: int) -> List[Dict[str, Any]]:
        """Search for domains using a specific technology."""
        leads = []
        try:
            resp = requests.get(
                f"{BASE_URL}/lists9/api.json",
                params={"KEY": self.api_key, "TECH": technology, "AMOUNT": min(limit, 50)},
                timeout=30,
            )
            self._api_calls += 1

            if resp.status_code == 429:
                raise RateLimitError("BuiltWith tech search rate limit", partial_results=leads)
            resp.raise_for_status()
            data = resp.json()
        except RateLimitError:
            raise
        except Exception as e:
            logger.error("builtwith_tech_search_error", error=str(e))
            return leads

        sites = data.get("Results") or []
        for site in sites:
            domain = site.get("D", "")
            if domain:
                leads.append({
                    "client_name": domain.split(".")[0].title() if domain else "",
                    "industry": "Technology",
                    "state": "",
                    "city": "",
                    "domain": domain,
                    "source": "builtwith",
                    "source_url": f"https://builtwith.com/{domain}",
                    "job_title": f"Uses {technology}",
                    "job_link": f"https://{domain}",
                    "posting_date": None,
                    "employer_website": f"https://{domain}",
                    "metadata": {
                        "searched_technology": technology,
                        "tech_stack": [],
                        "tech_age": None,
                    },
                })

        return leads

    def normalize(self, raw_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Normalize BuiltWith result to standard lead format."""
        try:
            domain = raw_data.get("domain", "")
            result = raw_data.get("result", {})
            if not domain:
                return None

            # Extract technologies by category
            paths = result.get("Result", {}).get("Paths") or []
            tech_categories = {}
            all_techs = []

            for path in paths:
                techs = path.get("Technologies") or []
                for tech in techs:
                    tech_name = tech.get("Name", "")
                    category = tech.get("Tag", "")
                    if tech_name:
                        all_techs.append(tech_name)
                        if category not in tech_categories:
                            tech_categories[category] = []
                        tech_categories[category].append(tech_name)

            # Identify CMS, frameworks, analytics
            cms = tech_categories.get("cms", [])
            frameworks = tech_categories.get("javascript-framework", []) + tech_categories.get("web-framework", [])
            analytics = tech_categories.get("analytics", [])

            # Determine tech age signal
            tech_age = None
            for path in paths:
                for tech in (path.get("Technologies") or []):
                    first_detected = tech.get("FirstDetected")
                    if first_detected and (tech_age is None or first_detected < tech_age):
                        tech_age = first_detected

            company_name = domain.split(".")[0].title()
            # Check for meta info
            meta = result.get("Result", {}).get("Meta", {})
            if meta.get("CompanyName"):
                company_name = meta["CompanyName"]

            return {
                "client_name": company_name,
                "industry": "Technology",
                "state": meta.get("State", ""),
                "city": meta.get("City", ""),
                "domain": domain,
                "source": "builtwith",
                "source_url": f"https://builtwith.com/{domain}",
                "job_title": f"Tech Stack: {', '.join(all_techs[:3])}" if all_techs else "Website",
                "job_link": f"https://{domain}",
                "posting_date": None,
                "employer_website": f"https://{domain}",
                "metadata": {
                    "tech_stack": all_techs[:20],
                    "cms": cms[:3],
                    "frameworks": frameworks[:5],
                    "analytics": analytics[:5],
                    "tech_categories": {k: v[:3] for k, v in list(tech_categories.items())[:10]},
                    "tech_age": tech_age,
                    "company_name": meta.get("CompanyName", ""),
                },
            }
        except Exception as e:
            logger.warning("builtwith_normalize_error", error=str(e))
            return None

    @property
    def source_name(self) -> str:
        return "builtwith"
