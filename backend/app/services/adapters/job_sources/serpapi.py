"""SerpAPI Google Jobs adapter — scrapes Google Jobs search results.

SerpAPI provides structured data from Google Jobs, catching postings not on other boards.
Sign up at https://serpapi.com/ to get an API key.

Pricing: Free: 100 searches/month | Paid: from $50/month
"""
import time
import random
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Optional
import httpx
from app.services.adapters.base import JobSourceAdapter, RateLimitError
from app.core.config import settings


class SerpAPIAdapter(JobSourceAdapter):
    """Adapter for SerpAPI Google Jobs search."""

    BASE_URL = "https://serpapi.com/search"

    def __init__(self, api_key: str = None):
        self.api_key = api_key or getattr(settings, 'SERPAPI_API_KEY', None)
        self._api_calls = 0

    @property
    def api_calls_made(self) -> int:
        return self._api_calls

    def test_connection(self) -> bool:
        """Test connection to SerpAPI using the lightweight account endpoint."""
        if not self.api_key:
            return False
        try:
            with httpx.Client() as client:
                response = client.get(
                    "https://serpapi.com/account.json",
                    params={"api_key": self.api_key},
                    timeout=15,
                )
                if response.status_code == 200:
                    data = response.json()
                    return data.get("account_status") == "Active"
                return False
        except Exception:
            return False

    def fetch_jobs(
        self,
        location: str = "United States",
        posted_within_days: int = 30,
        industries: Optional[List[str]] = None,
        exclude_keywords: Optional[List[str]] = None,
        job_titles: Optional[List[str]] = None,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        """Fetch jobs from Google Jobs via SerpAPI."""
        if not self.api_key:
            raise ValueError(
                "SerpAPI key not configured. "
                "Get one at https://serpapi.com/"
            )

        jobs = []
        search_titles = job_titles or getattr(settings, 'TARGET_JOB_TITLES', None) or [
            "HR Manager", "Operations Manager", "Warehouse Manager",
        ]

        # Map days to Google Jobs date filter chips
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

        # Batch titles (4 per query using OR)
        batched_queries = []
        for i in range(0, len(search_titles), 4):
            batch = search_titles[i:i+4]
            batched_queries.append(" OR ".join(batch))

        with httpx.Client(timeout=30) as client:
            for query in batched_queries:
                try:
                    # Google Jobs supports offset-based pagination via `start` param
                    for start_offset in range(0, 30, 10):  # 3 pages: 0, 10, 20
                        params = {
                            "engine": "google_jobs",
                            "q": query,
                            "location": location,
                            "api_key": self.api_key,
                            "chips": f"date_posted:{date_filter}",
                            "start": start_offset,
                        }

                        self._api_calls += 1
                        response = client.get(self.BASE_URL, params=params, timeout=30)
                        if response.status_code == 429:
                            for retry in range(3):
                                wait = min(60, (2 ** retry) + random.uniform(0, 1))
                                print(f"SerpAPI 429, retrying in {wait:.1f}s (attempt {retry + 1})")
                                time.sleep(wait)
                                self._api_calls += 1
                                response = client.get(self.BASE_URL, params=params, timeout=30)
                                if response.status_code != 429:
                                    break
                        response.raise_for_status()
                        data = response.json()

                        results = data.get("jobs_results", [])
                        if not results:
                            break  # No more results for this query

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

                        if len(jobs) >= limit:
                            break

                    if len(jobs) >= limit:
                        break

                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 429:
                        print(f"SerpAPI rate limit hit after {len(jobs)} jobs.")
                        break
                    print(f"SerpAPI error: {e}")
                except Exception as e:
                    print(f"SerpAPI error: {e}")
                    continue

        print(f"SerpAPI total: {len(jobs)} jobs from {len(batched_queries)} queries")
        return jobs

    def normalize(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize Google Jobs result to standard format."""
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

        # Extract state from location
        location = raw_data.get("location", "") or ""
        state = ""
        city = ""
        if location:
            parts = [p.strip() for p in location.split(",")]
            if parts:
                city = parts[0]
            for part in parts:
                clean = part.strip()
                if len(clean) == 2 and clean.isalpha():
                    state = clean.upper()
                    break

        # Extract salary from extensions
        salary_min = None
        salary_max = None
        salary_str = detected_extensions.get("salary", "")
        if salary_str and "$" in salary_str:
            import re
            amounts = re.findall(r'[\d,]+(?:\.\d+)?', salary_str.replace(",", ""))
            if len(amounts) >= 2:
                salary_min = float(amounts[0])
                salary_max = float(amounts[1])
            elif len(amounts) == 1:
                salary_min = float(amounts[0])

        # Get job link
        apply_options = raw_data.get("apply_options", [])
        job_link = ""
        if apply_options:
            job_link = apply_options[0].get("link", "")
        if not job_link:
            job_link = raw_data.get("share_link", "") or raw_data.get("job_id", "")

        return {
            "client_name": raw_data.get("company_name", "Unknown Company"),
            "job_title": raw_data.get("title", "Unknown Position"),
            "state": state,
            "posting_date": posting_date,
            "job_link": job_link,
            "salary_min": salary_min,
            "salary_max": salary_max,
            "source": "serpapi",
            "external_job_id": raw_data.get("job_id", ""),
            "city": city,
            "employer_linkedin_url": "",
            "employer_website": "",
            "job_publisher": "google_jobs",
        }
