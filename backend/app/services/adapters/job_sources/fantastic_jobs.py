"""Fantastic.jobs (Active Jobs DB) job-source adapter — LinkedIn feed at scale.

Fantastic.jobs aggregates the LinkedIn / Wellfound / Y Combinator job-board feed
(plus 200k ATS career sites) and returns company firmographics + AI enrichment on
EVERY job, with server-side filters for company size, industry, freshness and
agency-removal — exactly the Exzelon ICP. This is the recommended LinkedIn source
(see Job_Sourcing_Architecture_LinkedIn_Indeed_Glassdoor.docx).

Available via RapidAPI ("Active Jobs DB", host active-jobs-db.p.rapidapi.com) or
the direct API. Feed paths embed the window: /active-jb-7d, /active-jb-24h.

Docs: https://developer.fantastic.jobs/  ·  Sample: https://files.fantastic.jobs/sample-jb.json
"""
from datetime import datetime, date
from typing import List, Dict, Any, Optional
import httpx

from app.services.adapters.base import JobSourceAdapter
from app.core.config import settings

# US state name → 2-letter code, for extracting `state` from derived locations.
_US_STATES = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR", "california": "CA",
    "colorado": "CO", "connecticut": "CT", "delaware": "DE", "florida": "FL", "georgia": "GA",
    "hawaii": "HI", "idaho": "ID", "illinois": "IL", "indiana": "IN", "iowa": "IA",
    "kansas": "KS", "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV", "new hampshire": "NH",
    "new jersey": "NJ", "new mexico": "NM", "new york": "NY", "north carolina": "NC",
    "north dakota": "ND", "ohio": "OH", "oklahoma": "OK", "oregon": "OR", "pennsylvania": "PA",
    "rhode island": "RI", "south carolina": "SC", "south dakota": "SD", "tennessee": "TN",
    "texas": "TX", "utah": "UT", "vermont": "VT", "virginia": "VA", "washington": "WA",
    "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY", "district of columbia": "DC",
}


class FantasticJobsAdapter(JobSourceAdapter):
    """Adapter for the Fantastic.jobs direct API LinkedIn job-board feed
    (data.fantastic.jobs/v1/active-jb, Bearer auth). The RapidAPI "Active Jobs
    DB" listing exposes only the career-site (ATS) feed, not active-jb, so the
    LinkedIn feed requires the direct API."""

    DEFAULT_HOST = "data.fantastic.jobs"

    def __init__(self, api_key: str = None, host: str = None):
        self.api_key = api_key or getattr(settings, "FANTASTIC_JOBS_API_KEY", None)
        self.host = host or getattr(settings, "FANTASTIC_JOBS_HOST", None) or self.DEFAULT_HOST
        self._api_calls = 0

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}"}

    @property
    def api_calls_made(self) -> int:
        return self._api_calls

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def test_connection(self) -> bool:
        """Test connection by requesting a single job."""
        if not self.api_key:
            return False
        try:
            with httpx.Client() as client:
                resp = client.get(
                    f"https://{self.host}/v1/active-jb",
                    params={"limit": 1, "time_frame": "7d", "location": "United States"},
                    headers=self._headers(),
                    timeout=30,
                )
                return resp.status_code == 200
        except httpx.HTTPError:
            return False

    # ── Fetch ────────────────────────────────────────────────────────────────
    def fetch_jobs(
        self,
        location: str = "United States",
        posted_within_days: int = 1,
        industries: Optional[List[str]] = None,
        exclude_keywords: Optional[List[str]] = None,
        job_titles: Optional[List[str]] = None,
        limit: int = 1000,
        tuning: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> List[Dict[str, Any]]:
        """Fetch LinkedIn job-board postings. Matches the pipeline's adapter
        contract (accepts ``limit`` and ``tuning``). ``tuning`` may carry
        ``max_pages`` and ``max_employee_count`` (job_source_tuning.fantastic_jobs.*)."""
        if not self.is_configured():
            return []

        _t = tuning or {}
        max_pages = int(_t.get("max_pages") or max(1, min(20, -(-limit // 100))))  # ceil(limit/100), capped
        max_employee_count = int(_t.get("max_employee_count") or 200)
        time_frame = "24h" if posted_within_days <= 1 else "7d"
        url = f"https://{self.host}/v1/active-jb"
        titles = job_titles or getattr(settings, "TARGET_JOB_TITLES", None) or []
        title_or = " OR ".join(f'"{t}"' for t in titles) if titles else None
        # Optional server-side industry exclusion (set by pipeline via instance attr).
        exclude_industries = getattr(self, "_exclude_industries", None)

        results: List[Dict[str, Any]] = []
        with httpx.Client() as client:
            for page in range(max_pages):
                params = {
                    "limit": 100,
                    "offset": page * 100,
                    "time_frame": time_frame,
                    "location": location,
                    # server-side ICP push. On active-jb the LinkedIn org fields
                    # (headcount/industry/agency) are ALWAYS returned — the
                    # include_basic_organization_details flag is active-ats ONLY
                    # and returns HTTP 400 here, so we must NOT send it.
                    "organization_headcount_gte": 1,
                    "organization_headcount_lt": (max_employee_count or 200) + 1,
                    # drop postings that duplicate an ATS-feed listing
                    "exclude_ats_duplicate": "true",
                }
                if title_or:
                    params["title"] = title_or
                if exclude_industries:
                    params["exclude_organization_industry"] = ",".join(exclude_industries)
                try:
                    resp = client.get(url, params=params, headers=self._headers(), timeout=60)
                    self._api_calls += 1
                    if resp.status_code != 200:
                        break
                    batch = resp.json()
                    batch = batch if isinstance(batch, list) else (batch.get("data") or batch.get("jobs") or [])
                except (httpx.HTTPError, ValueError):
                    break
                if not batch:
                    break
                for raw in batch:
                    results.append(self.normalize(raw))
                if len(batch) < 100:
                    break
        return results

    # ── Normalize ────────────────────────────────────────────────────────────
    def _state_from_locations(self, raw: Dict[str, Any]) -> str:
        # locations_derived like "Dallas, Texas, United States"; regions_derived ["Texas"]
        for loc in (raw.get("locations_derived") or []):
            parts = [p.strip() for p in str(loc).split(",")]
            for p in parts:
                code = _US_STATES.get(p.lower())
                if code:
                    return code
        for reg in (raw.get("regions_derived") or []):
            code = _US_STATES.get(str(reg).strip().lower())
            if code:
                return code
        return ""

    def normalize(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        # posting date
        dt = raw_data.get("date_posted") or raw_data.get("date_created")
        try:
            posting_date = datetime.fromisoformat(str(dt).replace("Z", "+00:00")).date() if dt else date.today()
        except (ValueError, TypeError):
            posting_date = date.today()

        # salary — prefer AI-derived, fall back to raw structured salary
        salary_min = raw_data.get("ai_salary_min_value")
        salary_max = raw_data.get("ai_salary_max_value")

        headcount = raw_data.get("org_linkedin_headcount")
        try:
            employee_count = int(headcount) if headcount is not None else None
        except (TypeError, ValueError):
            employee_count = None

        emp_type = raw_data.get("ai_employment_type") or raw_data.get("employment_type")
        if isinstance(emp_type, list):
            emp_type = emp_type[0] if emp_type else ""

        cities = raw_data.get("cities_derived") or []
        return {
            "client_name": raw_data.get("organization") or "Unknown Company",
            "job_title": raw_data.get("title", "Unknown Position"),
            "state": self._state_from_locations(raw_data),
            "city": cities[0] if cities else "",
            "posting_date": posting_date,
            "job_link": raw_data.get("url") or "",
            "salary_min": float(salary_min) if salary_min else None,
            "salary_max": float(salary_max) if salary_max else None,
            "source": "fantastic_jobs",
            "employment_type": emp_type or "",
            "external_job_id": str(raw_data.get("id", "")) if raw_data.get("id") else "",
            "employer_linkedin_url": raw_data.get("organization_url") or "",
            "employer_website": raw_data.get("org_linkedin_website") or "",
            "industry": raw_data.get("org_linkedin_industry") or "",
            "company_size": str(employee_count) if employee_count else (raw_data.get("org_linkedin_size") or ""),
            "employee_count": employee_count,
            "is_staffing_agency": bool(raw_data.get("org_linkedin_recruitment_agency_derived")),
            "recruiter_name": raw_data.get("recruiter_name") or "",
            "recruiter_title": raw_data.get("recruiter_title") or "",
            "recruiter_url": raw_data.get("recruiter_url") or "",
            "job_publisher": raw_data.get("source") or "linkedin",
        }
