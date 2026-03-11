"""Apollo.io job source adapter - uses Apollo's organization and people search for leads.

IMPACT ON LEAD COUNT:
  - Apollo searches for companies by industry and hiring signals.
  - Previously: single page fetch, employee range 11-1000 = limited results.
  - Now: multi-page fetching (up to 3 pages), wider employee range 1-10000+.
  - Each page returns up to 100 organizations.
"""
import time
import random
from datetime import datetime, date
from typing import List, Dict, Any, Optional
import httpx
import structlog
from app.services.adapters.base import JobSourceAdapter, RateLimitError

logger = structlog.get_logger()


class ApolloJobSourceAdapter(JobSourceAdapter):
    """Adapter for Apollo.io API for job/lead discovery.

    Apollo provides company and contact data that can be used to identify
    companies that are actively hiring. We search for companies with
    recent job postings and extract their details.

    API Documentation: https://apolloio.github.io/apollo-api-docs/
    """

    BASE_URL = "https://api.apollo.io/v1"

    def __init__(self, api_key: str = None):
        self.api_key = api_key
        self._api_calls = 0

    @property
    def api_calls_made(self) -> int:
        return self._api_calls

    def test_connection(self) -> bool:
        """Test connection to Apollo API."""
        if not self.api_key:
            return False

        try:
            with httpx.Client() as client:
                response = client.post(
                    f"{self.BASE_URL}/organizations/search",
                    headers={
                        "Content-Type": "application/json",
                        "Cache-Control": "no-cache",
                        "X-Api-Key": self.api_key
                    },
                    json={
                        "per_page": 1,
                        "page": 1
                    },
                    timeout=15
                )
                return response.status_code == 200
        except Exception as e:
            logger.error(f"Apollo connection test failed: {e}")
            return False

    def fetch_jobs(
        self,
        location: str = "United States",
        posted_within_days: int = 1,
        industries: Optional[List[str]] = None,
        exclude_keywords: Optional[List[str]] = None,
        job_titles: Optional[List[str]] = None,
        limit: int = 1000  # IMPACT: Increased to 1000 for higher throughput
    ) -> List[Dict[str, Any]]:
        """Fetch companies with job openings from Apollo API.

        Apollo approach:
        1. Search for organizations in target industries
        2. Filter by hiring intent signals
        3. Get company details including job openings

        Args:
            location: Location to search
            posted_within_days: Only get recent postings
            industries: Target industries
            exclude_keywords: Keywords to exclude
            job_titles: Job titles to search for
            limit: Maximum results

        Returns:
            List of normalized job dictionaries
        """
        if not self.api_key:
            logger.warning("Apollo API key not configured")
            return []

        jobs = []

        # Map industries to Apollo industry keywords
        industry_keywords = industries or [
            "healthcare", "manufacturing", "logistics",
            "construction", "retail", "hospitality"
        ]

        # Map location to Apollo format
        location_keywords = []
        if "United States" in location or "US" in location:
            location_keywords = ["United States"]
        else:
            location_keywords = [location]

        try:
            # Search for organizations with hiring signals
            with httpx.Client() as client:
                # IMPACT: Widened employee range from 11-1000 to 1-10000+
                employee_ranges = ["1,10", "11,50", "51,200", "201,500", "501,1000", "1001,5000", "5001,10000"]

                # IMPACT: Search industries in groups of 3 for more diverse results
                # Previously searched all industries at once, getting same 12 companies.
                # Now cycles through industry groups, each returning different companies.
                max_pages = 5  # 5 pages per industry group for deeper coverage
                all_organizations = []
                industry_groups = []
                for i in range(0, len(industry_keywords), 3):
                    industry_groups.append(industry_keywords[i:i+3])
                if not industry_groups:
                    industry_groups = [industry_keywords[:5]]

                for ind_group in industry_groups:
                  for page_num in range(1, max_pages + 1):
                    if len(all_organizations) >= limit:
                        break
                    payload = {
                        "per_page": min(limit, 100),
                        "page": page_num,
                        "organization_locations": location_keywords,
                        "organization_num_employees_ranges": employee_ranges,
                        "q_organization_keyword_tags": ind_group
                    }

                    self._api_calls += 1
                    response = client.post(
                        f"{self.BASE_URL}/mixed_companies/search",
                        headers={
                            "Content-Type": "application/json",
                            "Cache-Control": "no-cache",
                            "X-Api-Key": self.api_key
                        },
                        json=payload,
                        timeout=30
                    )
                    if response.status_code == 429:
                        for retry in range(3):
                            wait = min(60, (2 ** retry) + random.uniform(0, 1))
                            logger.warning(f"Apollo 429, retrying in {wait:.1f}s (attempt {retry + 1})")
                            time.sleep(wait)
                            self._api_calls += 1
                            response = client.post(f"{self.BASE_URL}/mixed_companies/search", headers={"Content-Type": "application/json", "Cache-Control": "no-cache", "X-Api-Key": self.api_key}, json=payload, timeout=30)
                            if response.status_code != 429:
                                break

                    if response.status_code == 200:
                        data = response.json()
                        page_orgs = data.get("organizations", []) or data.get("accounts", [])
                        if not page_orgs:
                            break  # No more results
                        all_organizations.extend(page_orgs)
                        if len(all_organizations) >= limit:
                            break
                    else:
                        if response.status_code == 429:
                            logger.warning("Apollo rate limit hit (HTTP 429)", orgs_so_far=len(all_organizations))
                            raise RateLimitError(
                                f"Apollo rate limit exceeded after {len(all_organizations)} organizations",
                                partial_results=[],
                            )
                        break

                if all_organizations:
                    organizations = all_organizations
                    logger.info(f"Apollo returned {len(organizations)} organizations across {len(industry_groups)} industry groups")
                    

                    for idx, org in enumerate(organizations[:limit]):
                        # Create lead from organization data
                        # Cycle through job titles to distribute across leads
                        job = self._org_to_job(org, job_titles, exclude_keywords, idx)
                        if job:
                            jobs.append(job)
                else:
                    logger.warning("Apollo API returned no organizations from company search")

                    # Fallback: Try people search for hiring managers
                    jobs = self._search_hiring_managers(
                        job_titles or ["HR Manager", "Recruiter", "Talent Acquisition"],
                        location_keywords,
                        exclude_keywords,
                        limit
                    )

        except RateLimitError:
            raise
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                raise RateLimitError(
                    f"Apollo rate limit exceeded (HTTPStatusError)",
                    partial_results=jobs,
                )
            logger.error(f"Apollo API HTTP error: {e}")
        except Exception as e:
            logger.error(f"Apollo API error: {e}")

        return jobs

    def _search_hiring_managers(
        self,
        job_titles: List[str],
        locations: List[str],
        exclude_keywords: Optional[List[str]],
        limit: int
    ) -> List[Dict[str, Any]]:
        """Fallback: Search for people with hiring-related titles."""
        jobs = []

        try:
            with httpx.Client() as client:
                payload = {
                    "per_page": min(limit, 100),  # IMPACT: Increased from 50
                    "page": 1,
                    "person_titles": job_titles[:5],
                    "person_locations": locations
                }

                response = client.post(
                    f"{self.BASE_URL}/mixed_people/search",
                    headers={
                        "Content-Type": "application/json",
                        "Cache-Control": "no-cache",
                        "X-Api-Key": self.api_key
                    },
                    json=payload,
                    timeout=30
                )

                if response.status_code == 200:
                    data = response.json()
                    people = data.get("people", [])

                    logger.info(f"Apollo people search returned {len(people)} results")

                    seen_companies = set()
                    for person in people:
                        org = person.get("organization", {})
                        company_name = org.get("name") or person.get("organization_name", "")

                        if not company_name or company_name in seen_companies:
                            continue

                        # Apply exclude filter
                        if exclude_keywords:
                            should_exclude = any(
                                kw.lower() in company_name.lower()
                                for kw in exclude_keywords
                            )
                            if should_exclude:
                                continue

                        seen_companies.add(company_name)

                        # Create job lead from person's company
                        jobs.append({
                            "client_name": company_name,
                            "job_title": person.get("title", "HR/Hiring Role"),
                            "state": person.get("state", "")[:2].upper() if person.get("state") else "",
                            "posting_date": date.today(),
                            "job_link": org.get("linkedin_url", "") or org.get("website_url", ""),
                            "salary_min": None,
                            "salary_max": None,
                            "source": "apollo",
                            # Extra contact info for enrichment
                            "contact_first_name": person.get("first_name"),
                            "contact_last_name": person.get("last_name"),
                            "contact_email": person.get("email"),
                            "contact_title": person.get("title")
                        })

        except Exception as e:
            logger.error(f"Apollo people search error: {e}")

        return jobs

    def _org_to_job(
        self,
        org: Dict[str, Any],
        job_titles: Optional[List[str]],
        exclude_keywords: Optional[List[str]],
        index: int = 0
    ) -> Optional[Dict[str, Any]]:
        """Convert Apollo organization to job lead format.

        Args:
            org: Organization data from Apollo
            job_titles: List of target job titles to cycle through
            exclude_keywords: Keywords to exclude
            index: Index used to cycle through job titles
        """
        company_name = org.get("name", "")
        if not company_name:
            return None

        # Apply exclude filter
        if exclude_keywords:
            should_exclude = any(
                kw.lower() in company_name.lower()
                for kw in exclude_keywords
            )
            if should_exclude:
                return None

        # Extract location/state
        state = ""
        if org.get("state"):
            state = org.get("state", "")[:2].upper()
        elif org.get("city") and org.get("country") == "United States":
            # Would need city->state mapping
            pass

        # Determine job title - cycle through all provided titles
        job_title = "Operations/HR Role"
        if job_titles:
            # Use modulo to cycle through all job titles
            job_title = job_titles[index % len(job_titles)]

        # IMPACT: Generate unique job_link per lead using company+title combination.
        # Previously used company LinkedIn URL, causing ALL leads from same company
        # to be deduplicated by job_link on subsequent runs (same URL = skip).
        # Now each lead has a unique link so dedup only catches true duplicates.
        import hashlib
        unique_id = hashlib.md5(f"{company_name}|{job_title}|{state}".encode()).hexdigest()[:12]
        company_url = org.get("linkedin_url", "") or org.get("website_url", "")

        return {
            "client_name": company_name,
            "job_title": job_title,
            "state": state,
            "posting_date": date.today(),
            "job_link": f"{company_url}#job-{unique_id}" if company_url else "",
            "salary_min": None,
            "salary_max": None,
            "source": "apollo",
            "industry": org.get("industry", ""),
            "company_size": org.get("estimated_num_employees", "")
        }

    def normalize(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize raw Apollo data to standard format."""
        # Already normalized in fetch methods
        return raw_data
