"""Jooble job source adapter — free 71-country job aggregator.

Jooble aggregates jobs from thousands of job boards across 71 countries.
Sign up at https://jooble.org/api/about to get an API key.

Pricing: FREE — generous rate limits
"""
import time
import random
from datetime import datetime, date
from typing import List, Dict, Any, Optional
import httpx
from app.services.adapters.base import JobSourceAdapter, RateLimitError
from app.core.config import settings


class JoobleAdapter(JobSourceAdapter):
    """Adapter for Jooble job search API."""

    BASE_URL_TEMPLATE = "https://jooble.org/api/{api_key}"

    def __init__(self, api_key: str = None):
        self.api_key = api_key or getattr(settings, 'JOOBLE_API_KEY', None)
        self._api_calls = 0

    @property
    def api_calls_made(self) -> int:
        return self._api_calls

    @property
    def _url(self) -> str:
        return self.BASE_URL_TEMPLATE.format(api_key=self.api_key)

    def test_connection(self) -> bool:
        """Test connection to Jooble API."""
        if not self.api_key:
            return False
        try:
            with httpx.Client() as client:
                self._api_calls += 1
                response = client.post(
                    self._url,
                    json={"keywords": "Manager", "location": "United States", "page": 1},
                    timeout=15,
                )
                return response.status_code == 200
        except Exception:
            return False

    def _request_with_backoff(self, client: httpx.Client, payload: dict, max_retries: int = 3) -> httpx.Response:
        """Make request with exponential backoff on 429."""
        for attempt in range(max_retries + 1):
            self._api_calls += 1
            response = client.post(self._url, json=payload, timeout=30)
            if response.status_code == 429:
                if attempt < max_retries:
                    wait = min(60, (2 ** attempt) + random.uniform(0, 1))
                    print(f"Jooble rate limit, retrying in {wait:.1f}s (attempt {attempt + 1})")
                    time.sleep(wait)
                    continue
                raise RateLimitError("Jooble rate limit exceeded after retries")
            response.raise_for_status()
            return response
        raise RateLimitError("Jooble rate limit exceeded")

    def fetch_jobs(
        self,
        location: str = "United States",
        posted_within_days: int = 30,
        industries: Optional[List[str]] = None,
        exclude_keywords: Optional[List[str]] = None,
        job_titles: Optional[List[str]] = None,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        """Fetch jobs from Jooble API."""
        if not self.api_key:
            raise ValueError("Jooble API key not configured. Get one free at https://jooble.org/api/about")

        jobs = []
        search_titles = job_titles or getattr(settings, 'TARGET_JOB_TITLES', None) or [
            "HR Manager", "Operations Manager", "Warehouse Manager",
        ]

        # Batch titles into groups of 4
        title_batches = [search_titles[i:i+4] for i in range(0, len(search_titles), 4)]

        with httpx.Client(timeout=30) as client:
            for batch in title_batches:
                if len(jobs) >= limit:
                    break

                keywords = " | ".join(batch)

                # Paginate (1-based pages)
                for page in range(1, 6):  # Max 5 pages per query
                    if len(jobs) >= limit:
                        break

                    payload = {
                        "keywords": keywords,
                        "location": location,
                        "page": page,
                    }

                    try:
                        response = self._request_with_backoff(client, payload)
                        data = response.json()
                        items = data.get("jobs", [])

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

                    except RateLimitError:
                        print(f"Jooble rate limit hit after {len(jobs)} jobs")
                        return jobs
                    except Exception as e:
                        print(f"Jooble error: {e}")
                        break

        print(f"Jooble total: {len(jobs)} jobs ({self._api_calls} API calls)")
        return jobs

    def normalize(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize Jooble API response to standard format."""
        if not raw_data:
            return None

        # Parse posting date
        date_str = raw_data.get("updated", "") or raw_data.get("date", "")
        try:
            # Jooble dates can be ISO format
            posting_date = datetime.fromisoformat(date_str.replace("Z", "+00:00")).date()
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

        # Extract salary
        salary_str = raw_data.get("salary", "") or ""
        salary_min = None
        salary_max = None
        if salary_str and "$" in salary_str:
            import re
            nums = re.findall(r'[\d,]+', salary_str.replace(",", ""))
            if len(nums) >= 2:
                try:
                    salary_min = float(nums[0])
                    salary_max = float(nums[1])
                except ValueError:
                    pass
            elif len(nums) == 1:
                try:
                    salary_min = float(nums[0])
                except ValueError:
                    pass

        # Source attribution from Jooble
        job_source = raw_data.get("source", "jooble")

        return {
            "client_name": raw_data.get("company", "Unknown Company"),
            "job_title": raw_data.get("title", "Unknown Position"),
            "state": state,
            "posting_date": posting_date,
            "job_link": raw_data.get("link", ""),
            "salary_min": salary_min,
            "salary_max": salary_max,
            "source": "jooble",
            "external_job_id": raw_data.get("id", ""),
            "city": city,
            "employer_linkedin_url": "",
            "employer_website": "",
            "job_publisher": job_source,
        }
