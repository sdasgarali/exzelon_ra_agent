"""JSearch API adapter (RapidAPI) - aggregates jobs from LinkedIn, Indeed, Glassdoor, etc.

IMPACT ON LEAD COUNT:
  - JSearch is the PRIMARY real job source, aggregating LinkedIn, Indeed, Glassdoor, ZipRecruiter.
  - Previously: only 4 job title queries, 1 page each, "today" date filter = ~10-20 leads.
  - Now: ALL job titles searched, multi-page fetching, 30-day date window = 100-500+ leads.
  - Requires a RapidAPI key (free tier: 500 requests/month).
"""
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Optional
import httpx
from app.services.adapters.base import JobSourceAdapter
from app.core.config import settings


class JSearchAdapter(JobSourceAdapter):
    """Adapter for JSearch API on RapidAPI.

    JSearch aggregates job postings from multiple sources:
    - LinkedIn
    - Indeed
    - Glassdoor
    - ZipRecruiter
    - And many more

    To use:
    1. Sign up at https://rapidapi.com/
    2. Subscribe to JSearch API: https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch
    3. Get your RapidAPI key
    4. Configure in Settings → Job Sources → JSearch API Key

    Pricing: Free tier includes 500 requests/month
    """

    BASE_URL = "https://jsearch.p.rapidapi.com"

    def __init__(self, api_key: str = None):
        self.api_key = api_key or getattr(settings, 'JSEARCH_API_KEY', None) or getattr(settings, 'RAPIDAPI_KEY', None)

    def test_connection(self) -> bool:
        """Test connection to JSearch API."""
        if not self.api_key:
            return False

        try:
            with httpx.Client() as client:
                response = client.get(
                    f"{self.BASE_URL}/search",
                    headers={
                        "X-RapidAPI-Key": self.api_key,
                        "X-RapidAPI-Host": "jsearch.p.rapidapi.com"
                    },
                    params={
                        "query": "HR Manager in Texas",
                        "num_pages": "1"
                    },
                    timeout=15
                )
                return response.status_code == 200
        except Exception:
            return False

    def _batch_queries(self, titles, location, batch_size=4):
        """Batch job titles into grouped search queries.

        IMPACT: Instead of 50+ separate API calls (one per title),
        groups 4 titles per query = ~13 API calls total.
        Each call with num_pages=10 returns up to 100 results.
        Total potential: 13 calls x 100 results = ~1,300 results.
        """
        queries = []
        for i in range(0, len(titles), batch_size):
            batch = titles[i:i + batch_size]
            query_part = " OR ".join(batch)
            queries.append(f"{query_part} in {location}")
        return queries

    def fetch_jobs(
        self,
        location: str = "United States",
        posted_within_days: int = 30,
        industries: Optional[List[str]] = None,
        exclude_keywords: Optional[List[str]] = None,
        job_titles: Optional[List[str]] = None,
        limit: int = 1000  # IMPACT: Increased from 500 for higher throughput
    ) -> List[Dict[str, Any]]:
        """Fetch jobs from JSearch API (aggregates LinkedIn, Indeed, Glassdoor).

        Args:
            location: Location to search
            posted_within_days: Only get jobs posted within this many days
            industries: Target industries
            exclude_keywords: Keywords to exclude
            job_titles: Specific job titles to search
            limit: Maximum results

        Returns:
            List of normalized job dictionaries
        """
        if not self.api_key:
            raise ValueError(
                "JSearch API key not configured. "
                "Get one at https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch"
            )

        jobs = []

        # Build search queries from settings or default
        search_queries = job_titles or getattr(settings, 'TARGET_JOB_TITLES', None) or [
            "HR Manager", "Operations Manager", "Warehouse Manager",
            "Production Supervisor", "Plant Manager", "Recruiter",
            "Logistics Manager", "Quality Manager", "Maintenance Manager"
        ]

        # Map posted_within_days to JSearch date_posted parameter
        date_posted_map = {
            1: "today",
            3: "3days",
            7: "week",
            30: "month"
        }
        date_posted = date_posted_map.get(
            min(posted_within_days, 30),
            "week" if posted_within_days <= 7 else "month"
        )

        # IMPACT: Batch titles into grouped queries to save API calls
        # 37 titles / 4 per batch = ~9 queries instead of 37
        search_queries = self._batch_queries(search_queries, location, batch_size=4)

        # Reuse a single HTTP client for all queries (connection pooling)
        with httpx.Client(timeout=30) as client:
          for query in search_queries:
            try:
                # IMPACT: num_pages=10 fetches 100 results per call
                response = client.get(
                    f"{self.BASE_URL}/search",
                    headers={
                        "X-RapidAPI-Key": self.api_key,
                        "X-RapidAPI-Host": "jsearch.p.rapidapi.com"
                    },
                    params={
                        "query": query,
                        "page": "1",
                        "num_pages": "10",  # IMPACT: 10 pages = 100 results per call
                        "date_posted": date_posted,
                        "remote_jobs_only": "false"
                    },
                    timeout=30
                )
                response.raise_for_status()
                data = response.json()

                for result in data.get("data", []):
                    job = self.normalize(result)

                    # Apply exclude keywords filter
                    if exclude_keywords and job:
                        should_exclude = False
                        job_text = f"{job['job_title']} {job['client_name']}".lower()
                        for keyword in exclude_keywords:
                            if keyword.lower() in job_text:
                                should_exclude = True
                                break
                        if should_exclude:
                            continue

                    if job:
                        jobs.append(job)
                        if len(jobs) >= limit:
                            return jobs

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    print(f"JSearch rate limit hit after {len(jobs)} jobs. Stopping.")
                    break
                print(f"JSearch API error: {str(e)}")
            except Exception as e:
                print(f"JSearch error: {str(e)}")
                continue

        print(f"JSearch total: {len(jobs)} jobs from {len(search_queries)} batched queries")

        return jobs

    def normalize(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize JSearch API response to standard format."""
        if not raw_data:
            return None

        # Parse posting date
        date_str = raw_data.get("job_posted_at_datetime_utc", "")
        try:
            posting_date = datetime.fromisoformat(date_str.replace("Z", "+00:00")).date()
        except:
            posting_date = date.today()

        # Extract state from location
        state = raw_data.get("job_state", "")
        if not state:
            # Try to extract from city
            city = raw_data.get("job_city", "")
            country = raw_data.get("job_country", "")
            if country == "US" and city:
                # Would need a city->state mapping for accuracy
                state = ""

        # Parse salary
        salary_min = raw_data.get("job_min_salary")
        salary_max = raw_data.get("job_max_salary")

        # Determine source from job_publisher
        publisher = raw_data.get("job_publisher", "").lower()
        if "linkedin" in publisher:
            source = "linkedin"
        elif "indeed" in publisher:
            source = "indeed"
        elif "glassdoor" in publisher:
            source = "glassdoor"
        elif "ziprecruiter" in publisher:
            source = "ziprecruiter"
        else:
            source = "jsearch"

        return {
            "client_name": raw_data.get("employer_name", "Unknown Company"),
            "job_title": raw_data.get("job_title", "Unknown Position"),
            "state": state[:2].upper() if state else "",
            "posting_date": posting_date,
            "job_link": raw_data.get("job_apply_link", "") or raw_data.get("job_google_link", ""),
            "salary_min": float(salary_min) if salary_min else None,
            "salary_max": float(salary_max) if salary_max else None,
            "source": source,
            # Enhanced dedup fields (use `or ""` since API returns null, not missing keys)
            "external_job_id": raw_data.get("job_id") or "",
            "city": raw_data.get("job_city") or "",
            "employer_linkedin_url": raw_data.get("employer_linkedin") or "",
            "employer_website": raw_data.get("employer_website") or "",
            "job_publisher": raw_data.get("job_publisher") or "",
        }
