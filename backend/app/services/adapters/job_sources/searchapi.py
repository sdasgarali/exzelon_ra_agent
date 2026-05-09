"""SearchAPI.io job source adapter — cheaper Google Jobs alternative.

SearchAPI.io provides Google Jobs results at lower cost than SerpAPI.
Sign up at https://www.searchapi.io/ to get an API key.

Pricing: From $40/mo for 4,000 searches (vs SerpAPI $50/mo for 5,000)
"""
import time
import random
from datetime import datetime, date, timedelta
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

        # Map days to Google Jobs date filter chips (same as SerpAPI)
        date_filter_map = {
            1: "today",
            3: "3days",
            7: "week",
            30: "month",
        }
        date_filter = date_filter_map.get(
            min(posted_within_days, 30),
            "week" if posted_within_days <= 7 else "month"
        )

        # Batch titles into groups of 4 for OR queries (unquoted, matching SerpAPI)
        title_batches = [search_titles[i:i+4] for i in range(0, len(search_titles), 4)]

        with httpx.Client(timeout=30) as client:
            for batch in title_batches:
                if len(jobs) >= limit:
                    break

                query = " OR ".join(batch)

                # Paginate with offset (start param, 10 per page)
                for start in range(0, 30, 10):  # 3 pages per batch
                    if len(jobs) >= limit:
                        break

                    params = {
                        "engine": "google_jobs",
                        "q": query,
                        "location": location,
                        "api_key": self.api_key,
                        "chips": f"date_posted:{date_filter}",
                        "start": start,
                    }

                    try:
                        response = self._request_with_backoff(client, params)
                        data = response.json()
                        # SearchAPI returns jobs under "jobs" key (not "jobs_results")
                        results = data.get("jobs", [])

                        if not results:
                            break

                        for result in results:
                            job = self.normalize(result)
                            if not job:
                                continue

                            if self.filter_excluded(
                                job,
                                exclude_keywords=exclude_keywords,
                                exclude_company_keywords=getattr(self, '_exclude_company', None),
                                exclude_title_keywords=getattr(self, '_exclude_title', None),
                                match_mode=getattr(self, '_match_mode', 'word_boundary'),
                            ):
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

        # Parse posting date from relative text like "3 days ago"
        detected_extensions = raw_data.get("detected_extensions", {})
        posted_at = detected_extensions.get("posted_at", "")
        posting_date = date.today()
        if posted_at:
            try:
                if "hour" in posted_at or "just" in posted_at:
                    posting_date = date.today()
                elif "day" in posted_at:
                    days = int("".join(filter(str.isdigit, posted_at)) or "1")
                    posting_date = date.today() - timedelta(days=days)
                elif "week" in posted_at:
                    weeks = int("".join(filter(str.isdigit, posted_at)) or "1")
                    posting_date = date.today() - timedelta(weeks=weeks)
                elif "month" in posted_at:
                    months = int("".join(filter(str.isdigit, posted_at)) or "1")
                    posting_date = date.today() - timedelta(days=months * 30)
            except Exception:
                posting_date = date.today()

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
        salary_min = None
        salary_max = None
        salary_str = detected_extensions.get("salary", "")
        if salary_str and "$" in salary_str:
            import re
            nums = re.findall(r'[\d,]+', salary_str.replace(",", ""))
            if len(nums) >= 2:
                salary_min = float(nums[0])
                salary_max = float(nums[1])
            elif len(nums) == 1:
                salary_min = float(nums[0])

        # Employment type: SearchAPI uses "schedule" (not "schedule_type")
        from app.services.adapters.base import normalize_employment_type
        emp_type = normalize_employment_type(detected_extensions.get("schedule", ""))

        # Get job link: apply_link directly on object, fallback to sharing_link
        job_link = raw_data.get("apply_link", "") or raw_data.get("sharing_link", "")

        return {
            "client_name": raw_data.get("company_name", "Unknown Company"),
            "job_title": raw_data.get("title", "Unknown Position"),
            "state": state,
            "posting_date": posting_date,
            "job_link": job_link,
            "salary_min": salary_min,
            "salary_max": salary_max,
            "source": "searchapi",
            "employment_type": emp_type,
            "external_job_id": "",
            "city": city,
            "employer_linkedin_url": "",
            "employer_website": "",
            "job_publisher": "google_jobs",
        }
