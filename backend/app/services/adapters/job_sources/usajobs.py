"""USAJOBS.gov job source adapter — free US federal job listings.

USAJOBS is the official US government job board. Zero compliance risk.
Sign up at https://developer.usajobs.gov/ to get an API key.

Pricing: FREE — no rate limits, public API
"""
import time
import random
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Optional
import httpx
from app.services.adapters.base import JobSourceAdapter, RateLimitError
from app.core.config import settings


class USAJobsAdapter(JobSourceAdapter):
    """Adapter for USAJOBS.gov API."""

    BASE_URL = "https://data.usajobs.gov/api/search"

    def __init__(self, api_key: str = None, email: str = None):
        self.api_key = api_key or getattr(settings, 'USAJOBS_API_KEY', None)
        self.email = email or getattr(settings, 'USAJOBS_EMAIL', None)
        self._api_calls = 0

    @property
    def api_calls_made(self) -> int:
        return self._api_calls

    def _headers(self) -> dict:
        return {
            "Authorization-Key": self.api_key or "",
            "User-Agent": self.email or "exzelon-ra-agent@example.com",
            "Host": "data.usajobs.gov",
        }

    def test_connection(self) -> bool:
        """Test connection to USAJOBS API."""
        if not self.api_key:
            return False
        try:
            with httpx.Client() as client:
                self._api_calls += 1
                response = client.get(
                    self.BASE_URL,
                    headers=self._headers(),
                    params={"Keyword": "Manager", "ResultsPerPage": 1},
                    timeout=15,
                )
                return response.status_code == 200
        except Exception:
            return False

    def _request_with_backoff(self, client: httpx.Client, params: dict, max_retries: int = 3) -> httpx.Response:
        """Make request with exponential backoff on 429."""
        for attempt in range(max_retries + 1):
            self._api_calls += 1
            response = client.get(self.BASE_URL, headers=self._headers(), params=params, timeout=30)
            if response.status_code == 429:
                if attempt < max_retries:
                    wait = min(60, (2 ** attempt) + random.uniform(0, 1))
                    print(f"USAJOBS rate limit, retrying in {wait:.1f}s (attempt {attempt + 1})")
                    time.sleep(wait)
                    continue
                raise RateLimitError("USAJOBS rate limit exceeded after retries")
            response.raise_for_status()
            return response
        raise RateLimitError("USAJOBS rate limit exceeded")

    def fetch_jobs(
        self,
        location: str = "United States",
        posted_within_days: int = 30,
        industries: Optional[List[str]] = None,
        exclude_keywords: Optional[List[str]] = None,
        job_titles: Optional[List[str]] = None,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        """Fetch jobs from USAJOBS API."""
        if not self.api_key:
            raise ValueError("USAJOBS API key not configured. Get one free at https://developer.usajobs.gov/")

        jobs = []
        search_titles = job_titles or getattr(settings, 'TARGET_JOB_TITLES', None) or [
            "HR Manager", "Operations Manager", "Warehouse Manager",
        ]

        # Batch titles in pairs (USAJOBS Keyword is simple text search)
        title_batches = [search_titles[i:i+2] for i in range(0, len(search_titles), 2)]

        # Date range for posted_within_days
        date_from = (date.today() - timedelta(days=posted_within_days)).strftime("%Y-%m-%d")

        with httpx.Client(timeout=30) as client:
            for batch in title_batches:
                if len(jobs) >= limit:
                    break

                keyword = " OR ".join(batch)

                # Paginate (1-based pages, 100 per page)
                for page in range(1, 6):  # Max 5 pages per query
                    if len(jobs) >= limit:
                        break

                    params = {
                        "Keyword": keyword,
                        "LocationName": "United States",
                        "DatePosted": str(posted_within_days),
                        "ResultsPerPage": 100,
                        "Page": page,
                    }

                    try:
                        response = self._request_with_backoff(client, params)
                        data = response.json()
                        search_result = data.get("SearchResult", {})
                        items = search_result.get("SearchResultItems", [])

                        if not items:
                            break

                        for item in items:
                            match_data = item.get("MatchedObjectDescriptor", {})
                            job = self.normalize(match_data)
                            if not job:
                                continue

                            if exclude_keywords:
                                job_text = f"{job['job_title']} {job['client_name']}".lower()
                                if any(kw.lower() in job_text for kw in exclude_keywords):
                                    continue

                            jobs.append(job)
                            if len(jobs) >= limit:
                                break

                        # Check if more pages exist
                        total_count = int(search_result.get("SearchResultCount", 0))
                        if page * 100 >= total_count:
                            break

                    except RateLimitError:
                        print(f"USAJOBS rate limit hit after {len(jobs)} jobs")
                        return jobs
                    except Exception as e:
                        print(f"USAJOBS error: {e}")
                        break

        print(f"USAJOBS total: {len(jobs)} jobs ({self._api_calls} API calls)")
        return jobs

    def normalize(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize USAJOBS API response to standard format."""
        if not raw_data:
            return None

        # Parse posting date
        date_str = raw_data.get("PublicationStartDate", "")
        try:
            posting_date = datetime.fromisoformat(date_str.replace("Z", "+00:00")).date()
        except Exception:
            posting_date = date.today()

        # Extract location (first location)
        locations = raw_data.get("PositionLocation", [])
        state = ""
        city = ""
        if locations:
            loc = locations[0]
            city = loc.get("CityName", "")
            # CountrySubDivisionCode is often the state abbreviation
            state_code = loc.get("CountrySubDivisionCode", "")
            if state_code and len(state_code) >= 2:
                # Format can be "US-CA" or just "CA"
                state = state_code[-2:].upper() if "-" in state_code else state_code[:2].upper()

        # Extract salary
        salary_min = None
        salary_max = None
        remuneration = raw_data.get("PositionRemuneration", [])
        if remuneration:
            pay = remuneration[0]
            try:
                salary_min = float(pay.get("MinimumRange", 0))
                salary_max = float(pay.get("MaximumRange", 0))
                # Convert hourly to annual if needed
                rate = pay.get("RateIntervalCode", "")
                if rate == "Per Hour" and salary_min:
                    salary_min *= 2080
                    salary_max = (salary_max or 0) * 2080
            except (ValueError, TypeError):
                pass

        # Extract job URL
        apply_uri = raw_data.get("PositionURI", "")
        job_id = raw_data.get("PositionID", "")

        return {
            "client_name": raw_data.get("OrganizationName", "US Federal Government"),
            "job_title": raw_data.get("PositionTitle", "Unknown Position"),
            "state": state,
            "posting_date": posting_date,
            "job_link": apply_uri,
            "salary_min": salary_min,
            "salary_max": salary_max,
            "source": "usajobs",
            "external_job_id": f"usajobs-{job_id}" if job_id else "",
            "city": city,
            "employer_linkedin_url": "",
            "employer_website": "",
            "job_publisher": "usajobs.gov",
        }
