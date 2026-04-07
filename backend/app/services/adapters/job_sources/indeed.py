"""Indeed job source adapter.

IMPACT ON LEAD COUNT:
  - Indeed requires a Publisher Partnership (not freely available).
  - When configured: searches all job titles with 30-day window.
  - Previously: limited to 5 queries with 1-day window.
"""
from datetime import datetime, date
from typing import List, Dict, Any, Optional
import httpx
from app.services.adapters.base import JobSourceAdapter
from app.core.config import settings


class IndeedAdapter(JobSourceAdapter):
    """Adapter for Indeed Job Search API.

    Note: Indeed's API requires publisher partnership.
    Alternative: Use Indeed's RSS feeds or web scraping with proper permissions.

    For production use:
    1. Apply for Indeed Publisher Program: https://www.indeed.com/publisher
    2. Or use a third-party job aggregator API like:
       - Adzuna API (https://developer.adzuna.com/)
       - The Muse API (https://www.themuse.com/developers/api/v2)
       - JSearch API on RapidAPI (https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch)
    """

    BASE_URL = "https://api.indeed.com/ads/apisearch"

    def __init__(self, api_key: str = None, publisher_id: str = None):
        self.api_key = api_key or getattr(settings, 'INDEED_API_KEY', None)
        self.publisher_id = publisher_id or getattr(settings, 'INDEED_PUBLISHER_ID', None)

    def test_connection(self) -> bool:
        """Test connection to Indeed API."""
        if not self.publisher_id:
            return False

        try:
            # Indeed uses publisher ID for authentication
            with httpx.Client() as client:
                response = client.get(
                    self.BASE_URL,
                    params={
                        "publisher": self.publisher_id,
                        "q": "test",
                        "l": "New York",
                        "limit": 1,
                        "format": "json",
                        "v": "2"
                    },
                    timeout=10
                )
                return response.status_code == 200
        except Exception:
            return False

    def fetch_jobs(
        self,
        location: str = "United States",
        posted_within_days: int = 30,  # IMPACT: Changed from 1 (today) to 30 days
        industries: Optional[List[str]] = None,
        exclude_keywords: Optional[List[str]] = None,
        job_titles: Optional[List[str]] = None,
        limit: int = 200  # IMPACT: Increased from 50 for more results
    ) -> List[Dict[str, Any]]:
        """Fetch jobs from Indeed API.

        Args:
            location: Location to search (city, state, or country)
            posted_within_days: Only get jobs posted within this many days
            industries: Target industries (used to build search query)
            exclude_keywords: Keywords to exclude from results
            job_titles: Specific job titles to search for
            limit: Maximum number of results

        Returns:
            List of normalized job dictionaries
        """
        if not self.publisher_id:
            raise ValueError("Indeed Publisher ID not configured. Apply at https://www.indeed.com/publisher")

        jobs = []

        # Build search queries based on job titles or industries
        search_queries = job_titles or [
            "HR Manager", "Operations Manager", "Warehouse Manager",
            "Production Supervisor", "Plant Manager", "Logistics Manager"
        ]

        for query in search_queries:  # IMPACT: Search ALL titles (was limited to 5)
            try:
                with httpx.Client() as client:
                    params = {
                        "publisher": self.publisher_id,
                        "q": query,
                        "l": location,
                        "limit": 25,  # IMPACT: Fixed at 25 per query (was divided by total queries)
                        "format": "json",
                        "v": "2",
                        "fromage": posted_within_days,  # Jobs posted within X days
                        "sort": "date"  # Sort by date
                    }

                    response = client.get(
                        self.BASE_URL,
                        params=params,
                        timeout=30
                    )
                    response.raise_for_status()
                    data = response.json()

                    for result in data.get("results", []):
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

            except Exception as e:
                print(f"Indeed API error for query '{query}': {str(e)}")
                continue

        return jobs

    def normalize(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize Indeed API response to standard format."""
        if not raw_data:
            return None

        # Parse the date
        date_str = raw_data.get("date", "")
        try:
            posting_date = datetime.strptime(date_str, "%a, %d %b %Y %H:%M:%S GMT").date()
        except (ValueError, TypeError, AttributeError):
            posting_date = date.today()

        # Extract state from location
        location = raw_data.get("formattedLocation", "")
        state = ""
        if location:
            parts = location.split(", ")
            if len(parts) >= 2:
                state = parts[-1][:2].upper()  # Get state code

        return {
            "client_name": raw_data.get("company", "Unknown Company"),
            "job_title": raw_data.get("jobtitle", "Unknown Position"),
            "state": state,
            "posting_date": posting_date,
            "job_link": raw_data.get("url", ""),
            "salary_min": None,  # Indeed doesn't always provide salary
            "salary_max": None,
            "source": "indeed"
        }
