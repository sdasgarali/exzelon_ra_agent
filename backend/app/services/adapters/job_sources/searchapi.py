"""SearchAPI.io job source adapter — cheaper Google Jobs alternative.

SearchAPI.io provides Google Jobs results at lower cost than SerpAPI.
Sign up at https://www.searchapi.io/ to get an API key.

Pricing: From $40/mo for 4,000 searches (vs SerpAPI $50/mo for 5,000)
"""
import time
import random
from datetime import datetime, date
from typing import List, Dict, Any, Optional
import httpx
from app.services.adapters.base import JobSourceAdapter, RateLimitError
from app.core.config import settings


class SearchAPIAdapter(JobSourceAdapter):
    """Adapter for SearchAPI.io Google Jobs search."""

    BASE_URL = "https://www.searchapi.io/api/v1/search"

    def __init__(self, api_key: str = None):
        self.api_key = api_key or getattr(settings, 'SEARCHAPI_API_KEY', None)
        self._api_calls = 0

    @property
    def api_calls_made(self) -> int:
        return self._api_calls

    def test_connection(self) -> bool:
        """Test connection to SearchAPI.io."""
        if not self.api_key:
            return False
        try:
            with httpx.Client() as client:
                self._api_calls += 1
                response = client.get(
                    self.BASE_URL,
                    params={
                        "engine": "google_jobs",
                        "q": "HR Manager",
                        "api_key": self.api_key,
                        "num": 1,
                    },
                    timeout=15,
                )
                return response.status_code == 200
        except Exception:
            return False

    def _request_with_backoff(self, client: httpx.Client, params: dict, max_retries: int = 3) -> httpx.Response:
        """Make request with exponential backoff on 429."""
        for attempt in range(max_retries + 1):
            self._api_calls += 1
            response = client.get(self.BASE_URL, params=params, timeout=30)
            if response.status_code == 429:
                if attempt < max_retries:
                    wait = min(60, (2 ** attempt) + random.uniform(0, 1))
                    print(f"SearchAPI rate limit, retrying in {wait:.1f}s (attempt {attempt + 1})")
                    time.sleep(wait)
                    continue
                raise RateLimitError("SearchAPI rate limit exceeded after retries")
            response.raise_for_status()
            return response
        raise RateLimitError("SearchAPI rate limit exceeded")

    def fetch_jobs(
        self,
        location: str = "United States",
        posted_within_days: int = 30,
        industries: Optional[List[str]] = None,
        exclude_keywords: Optional[List[str]] = None,
        job_titles: Optional[List[str]] = None,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        """Fetch jobs from SearchAPI.io Google Jobs engine."""
        if not self.api_key:
            raise ValueError("SearchAPI.io API key not configured")

        jobs = []
        search_titles = job_titles or getattr(settings, 'TARGET_JOB_TITLES', None) or [
            "HR Manager", "Operations Manager", "Warehouse Manager",
        ]

        # Batch titles into groups of 4 for OR queries
        title_batches = [search_titles[i:i+4] for i in range(0, len(search_titles), 4)]

        with httpx.Client(timeout=30) as client:
            for batch in title_batches:
                if len(jobs) >= limit:
                    break

                query = " OR ".join(f'"{t}"' for t in batch)

                # Paginate with offset (start param, 10 per page)
                for start in range(0, 30, 10):  # 3 pages per batch
                    if len(jobs) >= limit:
                        break

                    params = {
                        "engine": "google_jobs",
                        "q": query,
                        "location": location,
                        "api_key": self.api_key,
                        "start": start,
                    }

                    try:
                        response = self._request_with_backoff(client, params)
                        data = response.json()
                        results = data.get("jobs_results", [])

                        if not results:
                            break

                        for result in results:
                            job = self.normalize(result)
                            if not job:
                                continue

                            if exclude_keywords:
                                job_text = f"{job['job_title']} {job['client_name']}".lower()
                                if any(kw.lower() in job_text for kw in exclude_keywords):
                                    continue

                            jobs.append(job)
                            if len(jobs) >= limit:
                                break

                    except RateLimitError:
                        print(f"SearchAPI rate limit hit after {len(jobs)} jobs")
                        return jobs
                    except Exception as e:
                        print(f"SearchAPI error: {e}")
                        break

        print(f"SearchAPI total: {len(jobs)} jobs ({self._api_calls} API calls)")
        return jobs

    def normalize(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize SearchAPI.io Google Jobs response to standard format."""
        if not raw_data:
            return None

        # Parse posting date
        date_str = raw_data.get("detected_extensions", {}).get("posted_at", "")
        posting_date = date.today()  # Default to today

        # Extract location
        location = raw_data.get("location", "") or ""
        state = ""
        city = ""
        if location:
            parts = [p.strip() for p in location.split(",")]
            if parts:
                city = parts[0]
            for part in parts:
                stripped = part.strip()
                if len(stripped) == 2 and stripped.isalpha():
                    state = stripped.upper()
                    break

        # Extract salary from extensions
        extensions = raw_data.get("detected_extensions", {})
        salary_min = None
        salary_max = None
        salary_str = extensions.get("salary", "")
        if salary_str and "$" in salary_str:
            import re
            nums = re.findall(r'[\d,]+', salary_str.replace(",", ""))
            if len(nums) >= 2:
                salary_min = float(nums[0])
                salary_max = float(nums[1])
            elif len(nums) == 1:
                salary_min = float(nums[0])

        return {
            "client_name": raw_data.get("company_name", "Unknown Company"),
            "job_title": raw_data.get("title", "Unknown Position"),
            "state": state,
            "posting_date": posting_date,
            "job_link": raw_data.get("apply_link") or raw_data.get("share_link", ""),
            "salary_min": salary_min,
            "salary_max": salary_max,
            "source": "searchapi",
            "external_job_id": raw_data.get("job_id", ""),
            "city": city,
            "employer_linkedin_url": "",
            "employer_website": "",
            "job_publisher": "google_jobs",
        }
