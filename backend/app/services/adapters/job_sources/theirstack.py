"""TheirStack job source adapter — finds companies hiring based on tech stack data.

TheirStack provides job postings data from company career pages and tech stack analysis.
Sign up at https://theirstack.com/ to get an API key.

Pricing: Free: 100 requests/month | Paid: from $49/month
"""
from datetime import datetime, date
from typing import List, Dict, Any, Optional
import httpx
from app.services.adapters.base import JobSourceAdapter
from app.core.config import settings


class TheirStackAdapter(JobSourceAdapter):
    """Adapter for TheirStack job postings API."""

    BASE_URL = "https://api.theirstack.com/v1"

    def __init__(self, api_key: str = None):
        self.api_key = api_key or getattr(settings, 'THEIRSTACK_API_KEY', None)

    def test_connection(self) -> bool:
        """Test connection to TheirStack API."""
        if not self.api_key:
            return False
        try:
            with httpx.Client() as client:
                response = client.post(
                    f"{self.BASE_URL}/jobs/search",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "limit": 1,
                        "job_country_code_or": ["US"],
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
        limit: int = 500,
    ) -> List[Dict[str, Any]]:
        """Fetch jobs from TheirStack API."""
        if not self.api_key:
            raise ValueError(
                "TheirStack API key not configured. "
                "Get one at https://theirstack.com/"
            )

        jobs = []
        search_titles = job_titles or getattr(settings, 'TARGET_JOB_TITLES', None) or [
            "HR Manager", "Operations Manager", "Warehouse Manager",
        ]

        # TheirStack uses POST with JSON body for search
        payload = {
            "limit": min(limit, 100),
            "page": 0,
            "job_country_code_or": ["US"],
            "posted_at_max_age_days": posted_within_days,
            "job_title_or": search_titles[:20],  # API limit on title filters
            "order_by": [{"desc": True, "field": "date_posted"}],
        }

        with httpx.Client(timeout=30) as client:
            try:
                pages_to_fetch = max(1, limit // 100)
                for page in range(pages_to_fetch):
                    payload["page"] = page
                    response = client.post(
                        f"{self.BASE_URL}/jobs/search",
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                            "Content-Type": "application/json",
                        },
                        json=payload,
                        timeout=30,
                    )
                    response.raise_for_status()
                    data = response.json()

                    results = data.get("data", [])
                    if not results:
                        break

                    for result in results:
                        job = self.normalize(result)
                        if not job:
                            continue

                        # Apply exclude keywords filter
                        if exclude_keywords:
                            job_text = f"{job['job_title']} {job['client_name']}".lower()
                            if any(kw.lower() in job_text for kw in exclude_keywords):
                                continue

                        jobs.append(job)
                        if len(jobs) >= limit:
                            break

                    if len(jobs) >= limit:
                        break

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    print(f"TheirStack rate limit hit after {len(jobs)} jobs.")
                else:
                    print(f"TheirStack API error: {e}")
            except Exception as e:
                print(f"TheirStack error: {e}")

        print(f"TheirStack total: {len(jobs)} jobs")
        return jobs

    def normalize(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize TheirStack API response to standard format."""
        if not raw_data:
            return None

        # Parse posting date
        date_str = raw_data.get("date_posted", "")
        try:
            posting_date = datetime.fromisoformat(date_str.replace("Z", "+00:00")).date()
        except Exception:
            posting_date = date.today()

        # Extract state from location
        location = raw_data.get("job_location", "") or ""
        state = ""
        if location:
            parts = [p.strip() for p in location.split(",")]
            for part in parts:
                if len(part) == 2 and part.isalpha():
                    state = part.upper()
                    break

        # Extract city
        city = ""
        if location:
            parts = [p.strip() for p in location.split(",")]
            if parts:
                city = parts[0]

        salary_min = raw_data.get("min_annual_salary")
        salary_max = raw_data.get("max_annual_salary")

        return {
            "client_name": raw_data.get("company_name", "Unknown Company"),
            "job_title": raw_data.get("job_title", "Unknown Position"),
            "state": state,
            "posting_date": posting_date,
            "job_link": raw_data.get("url", "") or raw_data.get("job_url", ""),
            "salary_min": float(salary_min) if salary_min else None,
            "salary_max": float(salary_max) if salary_max else None,
            "source": "theirstack",
            "external_job_id": str(raw_data.get("id", "")) if raw_data.get("id") else "",
            "city": city,
            "employer_linkedin_url": raw_data.get("company_linkedin_url") or "",
            "employer_website": raw_data.get("company_url") or "",
            "job_publisher": "theirstack",
        }
