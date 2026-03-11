"""JobDataFeeds/Techmap job source adapter — bulk job data at ~$1/1,000 jobs.

JobDataFeeds provides bulk access to millions of job postings worldwide.
Best cost-per-job ratio for high-volume lead sourcing.
Sign up at https://jobdatafeeds.com/ for API access.

Pricing: $200-400/month for bulk access (~$1 per 1,000 jobs)
"""
import time
import random
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Optional
import httpx
from app.services.adapters.base import JobSourceAdapter, RateLimitError
from app.core.config import settings


class JobDataFeedsAdapter(JobSourceAdapter):
    """Adapter for JobDataFeeds/Techmap bulk job data API."""

    BASE_URL = "https://jobdatafeeds.com/api/v2/jobs"

    def __init__(self, api_key: str = None):
        self.api_key = api_key or getattr(settings, 'JOBDATAFEEDS_API_KEY', None)
        self._api_calls = 0

    @property
    def api_calls_made(self) -> int:
        return self._api_calls

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
        }

    def test_connection(self) -> bool:
        """Test connection to JobDataFeeds API."""
        if not self.api_key:
            return False
        try:
            with httpx.Client() as client:
                self._api_calls += 1
                response = client.get(
                    self.BASE_URL,
                    headers=self._headers(),
                    params={"country": "US", "page_size": 1, "page": 1},
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
                    print(f"JobDataFeeds rate limit, retrying in {wait:.1f}s (attempt {attempt + 1})")
                    time.sleep(wait)
                    continue
                raise RateLimitError("JobDataFeeds rate limit exceeded after retries")
            response.raise_for_status()
            return response
        raise RateLimitError("JobDataFeeds rate limit exceeded")

    def fetch_jobs(
        self,
        location: str = "United States",
        posted_within_days: int = 30,
        industries: Optional[List[str]] = None,
        exclude_keywords: Optional[List[str]] = None,
        job_titles: Optional[List[str]] = None,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        """Fetch jobs from JobDataFeeds API."""
        if not self.api_key:
            raise ValueError("JobDataFeeds API key not configured. Sign up at https://jobdatafeeds.com/")

        jobs = []
        search_titles = job_titles or getattr(settings, 'TARGET_JOB_TITLES', None) or [
            "HR Manager", "Operations Manager", "Warehouse Manager",
        ]

        # Batch titles into groups of 4
        title_batches = [search_titles[i:i+4] for i in range(0, len(search_titles), 4)]

        # Date filter
        date_from = (date.today() - timedelta(days=posted_within_days)).strftime("%Y-%m-%d")

        with httpx.Client(timeout=30) as client:
            for batch in title_batches:
                if len(jobs) >= limit:
                    break

                query = " OR ".join(batch)

                # Bulk pagination: 100 per page, up to 50 pages
                for page in range(1, 51):
                    if len(jobs) >= limit:
                        break

                    params = {
                        "country": "US",
                        "q": query,
                        "date_from": date_from,
                        "page_size": 100,
                        "page": page,
                    }

                    try:
                        response = self._request_with_backoff(client, params)
                        data = response.json()

                        # Response structure may vary — try common field names
                        items = data.get("jobs", data.get("results", data.get("data", [])))

                        if not items:
                            break

                        for item in items:
                            job = self.normalize(item)
                            if not job:
                                continue

                            if exclude_keywords:
                                job_text = f"{job['job_title']} {job['client_name']}".lower()
                                if any(kw.lower() in job_text for kw in exclude_keywords):
                                    continue

                            jobs.append(job)
                            if len(jobs) >= limit:
                                break

                        # Check if more pages
                        total = data.get("total", data.get("total_count", 0))
                        if page * 100 >= total:
                            break

                    except RateLimitError:
                        print(f"JobDataFeeds rate limit hit after {len(jobs)} jobs")
                        return jobs
                    except Exception as e:
                        print(f"JobDataFeeds error: {e}")
                        break

        print(f"JobDataFeeds total: {len(jobs)} jobs ({self._api_calls} API calls)")
        return jobs

    def normalize(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize JobDataFeeds API response to standard format."""
        if not raw_data:
            return None

        # Parse posting date
        date_str = raw_data.get("date_posted", raw_data.get("published_at", ""))
        try:
            posting_date = datetime.fromisoformat(date_str.replace("Z", "+00:00")).date()
        except Exception:
            posting_date = date.today()

        # Extract location
        location = raw_data.get("location", "") or ""
        city_field = raw_data.get("city", "")
        state_field = raw_data.get("state", "")

        state = ""
        city = city_field or ""
        if state_field:
            state = state_field.upper()[:2] if len(state_field) <= 2 else ""
        elif location:
            parts = [p.strip() for p in location.split(",")]
            if parts:
                city = city or parts[0]
            for part in parts:
                stripped = part.strip()
                if len(stripped) == 2 and stripped.isalpha():
                    state = stripped.upper()
                    break

        # Extract salary
        salary_min = raw_data.get("salary_min", raw_data.get("min_salary"))
        salary_max = raw_data.get("salary_max", raw_data.get("max_salary"))

        try:
            salary_min = float(salary_min) if salary_min else None
        except (ValueError, TypeError):
            salary_min = None
        try:
            salary_max = float(salary_max) if salary_max else None
        except (ValueError, TypeError):
            salary_max = None

        return {
            "client_name": raw_data.get("company", raw_data.get("company_name", "Unknown Company")),
            "job_title": raw_data.get("title", raw_data.get("job_title", "Unknown Position")),
            "state": state,
            "posting_date": posting_date,
            "job_link": raw_data.get("url", raw_data.get("apply_url", "")),
            "salary_min": salary_min,
            "salary_max": salary_max,
            "source": "jobdatafeeds",
            "external_job_id": str(raw_data.get("id", "")) if raw_data.get("id") else "",
            "city": city,
            "employer_linkedin_url": raw_data.get("company_linkedin", ""),
            "employer_website": raw_data.get("company_url", raw_data.get("company_website", "")),
            "job_publisher": "jobdatafeeds",
        }
