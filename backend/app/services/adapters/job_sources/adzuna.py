"""Adzuna job source adapter — UK-based job aggregator with good US coverage.

Adzuna aggregates job postings from multiple sources across 16 countries.
Sign up at https://developer.adzuna.com/ to get app_id and app_key.

Pricing: Free: 250 requests/month | Paid: from $99/month
"""
import time
import random
from datetime import datetime, date
from typing import List, Dict, Any, Optional
import httpx
from app.services.adapters.base import JobSourceAdapter, RateLimitError
from app.core.config import settings


class AdzunaAdapter(JobSourceAdapter):
    """Adapter for Adzuna job search API."""

    BASE_URL = "https://api.adzuna.com/v1/api/jobs/us/search"

    def __init__(self, app_id: str = None, api_key: str = None):
        self.app_id = app_id or getattr(settings, 'ADZUNA_APP_ID', None)
        self.api_key = api_key or getattr(settings, 'ADZUNA_API_KEY', None)
        self._api_calls = 0

    @property
    def api_calls_made(self) -> int:
        return self._api_calls

    def test_connection(self) -> bool:
        """Test connection to Adzuna API."""
        if not self.app_id or not self.api_key:
            return False
        try:
            with httpx.Client() as client:
                response = client.get(
                    f"{self.BASE_URL}/1",
                    params={
                        "app_id": self.app_id,
                        "app_key": self.api_key,
                        "results_per_page": 1,
                        "what": "Manager",
                        "where": "United States",
                    },
                    timeout=15,
                )
                return response.status_code == 200
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
        tuning: Optional[Dict] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch jobs from Adzuna API."""
        if not self.app_id or not self.api_key:
            raise ValueError(
                "Adzuna credentials not configured. "
                "Get app_id and app_key at https://developer.adzuna.com/"
            )

        jobs = []
        search_titles = job_titles or getattr(settings, 'TARGET_JOB_TITLES', None) or [
            "HR Manager", "Operations Manager", "Warehouse Manager",
        ]

        # Batch titles
        _t = tuning or {}
        _batch_size = int(_t.get('batch_size', 4))
        _max_pages = int(_t.get('max_pages', 10))
        _results_per_page = int(_t.get('results_per_page', 50))
        batched_queries = []
        for i in range(0, len(search_titles), _batch_size):
            batch = search_titles[i:i+_batch_size]
            batched_queries.append(" OR ".join(batch))

        # Adzuna supports a native `what_exclude` param (space-separated words to
        # exclude) — push exclusions server-side instead of filtering after fetch.
        neg_terms = self._negative_terms(exclude_keywords)
        what_exclude = " ".join(neg_terms) if neg_terms else None

        with httpx.Client(timeout=30) as client:
            for query in batched_queries:
                try:
                    # Adzuna uses page-based pagination (1-indexed)
                    for page in range(1, _max_pages + 1):
                        params = {
                            "app_id": self.app_id,
                            "app_key": self.api_key,
                            "results_per_page": _results_per_page,
                            "what": query,
                            "where": location,
                            "max_days_old": posted_within_days,
                            "sort_by": "date",
                        }
                        if what_exclude:
                            params["what_exclude"] = what_exclude

                        self._api_calls += 1
                        response = client.get(
                            f"{self.BASE_URL}/{page}",
                            params=params,
                            timeout=30,
                        )
                        if response.status_code == 429:
                            for retry in range(3):
                                wait = min(60, (2 ** retry) + random.uniform(0, 1))
                                print(f"Adzuna 429, retrying in {wait:.1f}s (attempt {retry + 1})")
                                time.sleep(wait)
                                self._api_calls += 1
                                response = client.get(f"{self.BASE_URL}/{page}", params=params, timeout=30)
                                if response.status_code != 429:
                                    break
                        response.raise_for_status()
                        data = response.json()

                        results = data.get("results", [])
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

                        if len(jobs) >= limit:
                            break

                    if len(jobs) >= limit:
                        break

                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 429:
                        print(f"Adzuna rate limit hit after {len(jobs)} jobs.")
                        break
                    print(f"Adzuna API error: {e}")
                except Exception as e:
                    print(f"Adzuna error: {e}")
                    continue

        print(f"Adzuna total: {len(jobs)} jobs from {len(batched_queries)} queries")
        return jobs

    def normalize(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize Adzuna API response to standard format."""
        if not raw_data:
            return None

        # Parse posting date
        date_str = raw_data.get("created", "")
        try:
            posting_date = datetime.fromisoformat(date_str.replace("Z", "+00:00")).date()
        except Exception:
            posting_date = date.today()

        # Extract location info
        location_data = raw_data.get("location", {})
        display_name = location_data.get("display_name", "") or ""
        area = location_data.get("area", []) or []

        state = ""
        city = ""
        if area:
            # Adzuna area is typically [country, state, city, ...]
            if len(area) >= 2:
                state_name = area[1] if len(area) > 1 else ""
                # Try to extract 2-letter state code
                if len(state_name) == 2 and state_name.isalpha():
                    state = state_name.upper()
            if len(area) >= 3:
                city = area[2]
        elif display_name:
            parts = [p.strip() for p in display_name.split(",")]
            if parts:
                city = parts[0]
            for part in parts:
                clean = part.strip()
                if len(clean) == 2 and clean.isalpha():
                    state = clean.upper()
                    break

        # Salary
        salary_min = raw_data.get("salary_min")
        salary_max = raw_data.get("salary_max")

        # Company name
        company = raw_data.get("company", {}) or {}
        company_name = company.get("display_name", "Unknown Company")

        # Employment type: Adzuna has contract_type (permanent/contract/temporary) + contract_time (full_time/part_time)
        from app.services.adapters.base import normalize_employment_type
        contract_type = raw_data.get("contract_type", "")  # permanent, contract, temporary, seasonal
        contract_time = raw_data.get("contract_time", "")  # full_time, part_time
        # Prefer contract_type if it's more specific than "permanent"; fall back to contract_time
        emp_raw = contract_type if contract_type and contract_type != "permanent" else contract_time
        if not emp_raw and contract_type == "permanent":
            emp_raw = "full_time"  # permanent → Full-time
        emp_type = normalize_employment_type(emp_raw or "")

        return {
            "client_name": company_name,
            "job_title": raw_data.get("title", "Unknown Position"),
            "state": state,
            "posting_date": posting_date,
            "job_link": raw_data.get("redirect_url", "") or raw_data.get("adref", ""),
            "salary_min": float(salary_min) if salary_min else None,
            "salary_max": float(salary_max) if salary_max else None,
            "source": "adzuna",
            "employment_type": emp_type,
            "external_job_id": str(raw_data.get("id", "")) if raw_data.get("id") else "",
            "city": city,
            "employer_linkedin_url": "",
            "employer_website": "",
            "job_publisher": "adzuna",
        }
