"""Coresignal Multi-Source Jobs adapter — the only provider that bundles
recruiter/hiring manager contacts directly with job posting data.

399M+ job records, 65+ data points per record. Sources: LinkedIn, Indeed,
Glassdoor, Wellfound. 6-hour data refresh cycle. ISO/GDPR/CCPA compliant.

Sign up at https://coresignal.com/ to get an API key.

Pricing:
  - Free trial: 200 credits (14 days)
  - Starter: $49/mo (250 credits)
  - Pro: $800/mo (10,000 credits)
  - Premium: $1,500/mo (50,000 credits)

Multi-source job records cost 2 credits each.
"""
import time
import random
from datetime import datetime, date
from typing import List, Dict, Any, Optional
import httpx
from app.services.adapters.base import JobSourceAdapter, RateLimitError
from app.core.config import settings


class CoresignalAdapter(JobSourceAdapter):
    """Adapter for Coresignal Multi-Source Jobs API.

    Unique differentiator: returns recruiter/hiring manager contact data
    alongside job postings, eliminating the separate contact enrichment step.
    """

    BASE_URL = "https://api.coresignal.com/cdapi/v1"

    def __init__(self, api_key: str = None):
        self.api_key = api_key or getattr(settings, 'CORESIGNAL_API_KEY', None)
        self._api_calls = 0

    @property
    def api_calls_made(self) -> int:
        return self._api_calls

    def test_connection(self) -> bool:
        """Test connection to Coresignal API with a minimal search."""
        if not self.api_key:
            return False
        try:
            with httpx.Client() as client:
                # Use the search endpoint with minimal filters
                response = client.post(
                    f"{self.BASE_URL}/multi_source/job/search/filter",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "country": "United States",
                        "title": "Manager",
                        "application_active": True,
                        "page_size": 1,
                    },
                    timeout=15,
                )
                if response.status_code != 200:
                    print(f"Coresignal test_connection: HTTP {response.status_code} - {response.text[:200]}")
                return response.status_code == 200
        except Exception as e:
            print(f"Coresignal test_connection exception: {type(e).__name__}: {e}")
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
        """Fetch jobs from Coresignal Multi-Source Jobs API.

        Uses the search/filter endpoint with POST body to query jobs.
        Paginates using page/page_size parameters.
        """
        if not self.api_key:
            raise ValueError(
                "Coresignal API key not configured. "
                "Get one at https://coresignal.com/"
            )

        jobs = []
        search_titles = job_titles or getattr(settings, 'TARGET_JOB_TITLES', None) or [
            "HR Manager", "Operations Manager", "Warehouse Manager",
        ]

        # Batch titles into groups of 5 for broader queries
        title_batches = []
        batch_size = 5
        for i in range(0, len(search_titles), batch_size):
            title_batches.append(search_titles[i:i + batch_size])

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        with httpx.Client(timeout=30) as client:
            for batch in title_batches:
                if len(jobs) >= limit:
                    break

                # Coresignal uses OR-style title search
                title_query = " OR ".join(f'"{t}"' for t in batch)

                payload = {
                    "country": "United States",
                    "title": title_query,
                    "application_active": True,
                    "created_at_gte": _days_ago_iso(posted_within_days),
                    "page_size": 100,
                    "page": 0,
                }

                pages_to_fetch = min(5, max(1, limit // 100))
                for page in range(pages_to_fetch):
                    if len(jobs) >= limit:
                        break

                    payload["page"] = page
                    self._api_calls += 1

                    try:
                        response = client.post(
                            f"{self.BASE_URL}/multi_source/job/search/filter",
                            headers=headers,
                            json=payload,
                            timeout=30,
                        )

                        if response.status_code == 429:
                            for retry in range(3):
                                wait = min(60, (2 ** retry) + random.uniform(0, 1))
                                print(f"Coresignal 429, retrying in {wait:.1f}s (attempt {retry + 1})")
                                time.sleep(wait)
                                self._api_calls += 1
                                response = client.post(
                                    f"{self.BASE_URL}/multi_source/job/search/filter",
                                    headers=headers,
                                    json=payload,
                                    timeout=30,
                                )
                                if response.status_code != 429:
                                    break

                        if response.status_code == 429:
                            raise RateLimitError(
                                "Coresignal API rate limit exceeded",
                                partial_results=jobs,
                            )

                        response.raise_for_status()
                        data = response.json()

                        # Handle both list and paginated dict responses
                        if isinstance(data, list):
                            results = data
                        elif isinstance(data, dict):
                            results = data.get("data", data.get("results", data.get("jobs", [])))
                        else:
                            results = []

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

                    except RateLimitError:
                        raise
                    except httpx.HTTPStatusError as e:
                        if e.response.status_code == 429:
                            print(f"Coresignal rate limit hit after {len(jobs)} jobs.")
                            raise RateLimitError(
                                f"Coresignal rate limit after {len(jobs)} jobs",
                                partial_results=jobs,
                            )
                        elif e.response.status_code == 402:
                            print(f"Coresignal credits exhausted after {len(jobs)} jobs.")
                            break
                        else:
                            print(f"Coresignal API error: {e}")
                            break
                    except Exception as e:
                        print(f"Coresignal error: {e}")
                        break

        print(f"Coresignal total: {len(jobs)} jobs")
        return jobs

    def normalize(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize Coresignal API response to standard format.

        Coresignal uniquely provides recruiter/contact data alongside job data.
        These are mapped to contact_first_name, contact_last_name, etc. so that
        the pipeline pre-populates lead contact info (similar to Apollo adapter).
        """
        if not raw_data:
            return None

        # Parse posting date
        date_str = raw_data.get("created", "") or raw_data.get("created_at", "") or ""
        try:
            if "T" in date_str:
                posting_date = datetime.fromisoformat(date_str.replace("Z", "+00:00")).date()
            elif date_str:
                posting_date = datetime.strptime(date_str[:10], "%Y-%m-%d").date()
            else:
                posting_date = date.today()
        except Exception:
            posting_date = date.today()

        # Extract location components
        location = raw_data.get("location", "") or ""
        city = raw_data.get("city", "") or ""
        state = raw_data.get("state", "") or raw_data.get("region", "") or ""
        country = raw_data.get("country", "") or ""

        # Parse state from location if not directly provided
        if not state and location:
            parts = [p.strip() for p in location.split(",")]
            for part in parts:
                cleaned = part.strip()
                if len(cleaned) == 2 and cleaned.isalpha():
                    state = cleaned.upper()
                    break

        # Parse city from location if not directly provided
        if not city and location:
            parts = [p.strip() for p in location.split(",")]
            if parts:
                city = parts[0]

        # Extract salary data
        salary_min = raw_data.get("salary_min") or raw_data.get("min_salary")
        salary_max = raw_data.get("salary_max") or raw_data.get("max_salary")

        # Company data
        company_name = (
            raw_data.get("company_name")
            or raw_data.get("company", {}).get("name", "")
            if isinstance(raw_data.get("company"), dict)
            else raw_data.get("company_name", "Unknown Company")
        )
        company_linkedin = (
            raw_data.get("company_linkedin_url")
            or raw_data.get("company", {}).get("linkedin_url", "")
            if isinstance(raw_data.get("company"), dict)
            else raw_data.get("company_linkedin_url", "")
        )
        company_website = (
            raw_data.get("company_website")
            or raw_data.get("company", {}).get("website", "")
            if isinstance(raw_data.get("company"), dict)
            else raw_data.get("company_website", "")
        )

        # UNIQUE: Extract recruiter/contact data (Coresignal's differentiator)
        # This pre-populates lead contact info, skipping the enrichment step
        recruiter = raw_data.get("recruiter", {}) or {}
        if isinstance(recruiter, dict):
            contact_first = recruiter.get("first_name", "") or ""
            contact_last = recruiter.get("last_name", "") or ""
            contact_email = recruiter.get("email", "") or ""
            contact_title = recruiter.get("title", "") or recruiter.get("headline", "") or ""
        else:
            contact_first = ""
            contact_last = ""
            contact_email = ""
            contact_title = ""

        # Job URL
        job_url = (
            raw_data.get("url")
            or raw_data.get("job_url")
            or raw_data.get("external_url")
            or raw_data.get("application_url")
            or ""
        )

        # External ID
        ext_id = raw_data.get("id") or raw_data.get("job_id") or ""

        # Source platform (linkedin, indeed, glassdoor, etc.)
        source_platform = raw_data.get("source", "") or raw_data.get("source_type", "") or "coresignal"

        result = {
            "client_name": company_name or "Unknown Company",
            "job_title": raw_data.get("title", "") or raw_data.get("job_title", "Unknown Position"),
            "state": state,
            "posting_date": posting_date,
            "job_link": job_url,
            "salary_min": float(salary_min) if salary_min else None,
            "salary_max": float(salary_max) if salary_max else None,
            "source": source_platform if source_platform != "coresignal" else "coresignal",
            "external_job_id": str(ext_id) if ext_id else "",
            "city": city,
            "employer_linkedin_url": company_linkedin or "",
            "employer_website": company_website or "",
            "job_publisher": "coresignal",
        }

        # Pre-populate contact data if available (unique to Coresignal)
        if contact_first or contact_email:
            result["contact_first_name"] = contact_first
            result["contact_last_name"] = contact_last
            result["contact_email"] = contact_email
            result["contact_title"] = contact_title

        return result


def _days_ago_iso(days: int) -> str:
    """Return ISO date string for N days ago."""
    from datetime import timedelta
    return (date.today() - timedelta(days=days)).isoformat()
