"""TheirStack job source adapter — finds companies hiring based on tech stack data.

TheirStack provides job postings data from company career pages and tech stack analysis.
Sign up at https://theirstack.com/ to get an API key.

Pricing: Free: 100 requests/month | Paid: from $49/month
"""
import time
import random
from datetime import datetime, date
from typing import List, Dict, Any, Optional
import httpx
from app.services.adapters.base import JobSourceAdapter, RateLimitError
from app.core.config import settings


class TheirStackAdapter(JobSourceAdapter):
    """Adapter for TheirStack job postings API."""

    BASE_URL = "https://api.theirstack.com/v1"

    # TheirStack caps results-per-page by plan tier. Free/entry plans allow only
    # 25 per page and return HTTP 403 (E-020 "Premium functionality limitation")
    # for anything larger. Requesting more silently yielded 0 leads. Override via
    # tuning ``max_results_per_page`` once on a plan that permits a higher cap.
    DEFAULT_MAX_RESULTS_PER_PAGE = 25

    def __init__(self, api_key: str = None):
        self.api_key = api_key or getattr(settings, 'THEIRSTACK_API_KEY', None)
        self._api_calls = 0

    @property
    def api_calls_made(self) -> int:
        return self._api_calls

    def _apply_firmographic_filters(self, payload: Dict[str, Any], tuning: Dict[str, Any]) -> Dict[str, Any]:
        """Push the business-rule firmographic filters into the search payload so
        they run server-side instead of being filtered out after fetch.

        Sourced from the per-adapter ``tuning`` dict (job_source_tuning.theirstack.*)
        and the exclusion attributes the pipeline sets on the adapter instance.
        """
        _t = tuning or {}

        # Company size: default ≤200 employees (business rule). Set tuning
        # ``max_employee_count: null`` to disable. ``include_unknown_size: true``
        # also keeps companies whose size TheirStack doesn't know (more volume,
        # but may include >200-employee firms).
        if "max_employee_count" in _t:
            max_emp = _t.get("max_employee_count")
        else:
            max_emp = getattr(settings, "THEIRSTACK_MAX_EMPLOYEE_COUNT", 200)
        if max_emp is not None:
            size_key = "max_employee_count_or_null" if _t.get("include_unknown_size") else "max_employee_count"
            payload[size_key] = int(max_emp)

        min_emp = _t.get("min_employee_count")
        if min_emp is not None:
            payload["min_employee_count"] = int(min_emp)

        # Industry (non-IT). Opt-in via tuning using LinkedIn Industry Codes V2 —
        # include only target industries and/or exclude IT industries. No hardcoded
        # defaults (codes are operator-configured in Source Tuning).
        if _t.get("industry_id_or"):
            payload["industry_id_or"] = list(_t["industry_id_or"])
        if _t.get("industry_id_not"):
            payload["industry_id_not"] = list(_t["industry_id_not"])

        # Exclusions pushed server-side (staffing agencies by company name, and
        # unwanted titles), gated by the shared push-negatives flag. The local
        # filter_excluded() backstop still runs regardless.
        if getattr(self, "_push_negatives", True):
            exclude_company = getattr(self, "_exclude_company", None)
            if exclude_company:
                payload["company_name_partial_match_not"] = list(exclude_company)
            exclude_title = getattr(self, "_exclude_title", None)
            if exclude_title:
                payload["job_title_not"] = list(exclude_title)

        return payload

    def _build_base_payload(self, posted_within_days: int, limit: int, tuning: Dict[str, Any]) -> Dict[str, Any]:
        """Build the base TheirStack search payload (firmographic filters included).

        ``job_title_or`` and ``page`` are set per-batch/per-page by the caller.
        """
        per_page = int((tuning or {}).get("max_results_per_page", self.DEFAULT_MAX_RESULTS_PER_PAGE))
        per_page = max(1, min(per_page, int(limit) if limit else per_page))
        payload = {
            "limit": per_page,
            "page": 0,
            "job_country_code_or": ["US"],
            "posted_at_max_age_days": posted_within_days,
            "order_by": [{"desc": True, "field": "date_posted"}],
        }
        self._apply_firmographic_filters(payload, tuning or {})
        return payload

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
                        "posted_at_max_age_days": 7,
                    },
                    timeout=15,
                )
                if response.status_code != 200:
                    print(f"TheirStack test_connection: HTTP {response.status_code} - {response.text[:200]}")
                return response.status_code == 200
        except Exception as e:
            print(f"TheirStack test_connection exception: {type(e).__name__}: {e}")
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
        _t = tuning or {}
        _batch_size = int(_t.get('batch_size', 20))
        _max_pages = int(_t.get('max_pages', 10))

        # Per-source hard cap on total results per run. TheirStack bills 1 API
        # credit per job returned, so this bounds monthly spend independently of
        # the global ``pipeline_adapter_limit``. Set via tuning
        # ``max_total_results`` (None/absent = unbounded, uses ``limit``).
        _max_total = _t.get('max_total_results')
        if _max_total is not None:
            limit = min(int(limit), int(_max_total))

        title_batches = [search_titles[i:i + _batch_size] for i in range(0, len(search_titles), _batch_size)]
        if not title_batches:
            title_batches = [search_titles]

        payload = self._build_base_payload(posted_within_days, limit, _t)
        per_page = payload.get("limit") or self.DEFAULT_MAX_RESULTS_PER_PAGE

        with httpx.Client(timeout=30) as client:
            try:
                # Ceil-divide so a small per-page cap still fetches enough pages
                # to reach the requested total (e.g. 25/page x 40 pages = 1000).
                pages_to_fetch = min(_max_pages, max(1, -(-limit // per_page)))
                for title_batch in title_batches:
                    payload["job_title_or"] = title_batch
                    for page in range(pages_to_fetch):
                        payload["page"] = page
                        self._api_calls += 1
                        response = client.post(
                            f"{self.BASE_URL}/jobs/search",
                            headers={
                                "Authorization": f"Bearer {self.api_key}",
                                "Content-Type": "application/json",
                            },
                            json=payload,
                            timeout=30,
                        )
                        if response.status_code == 429:
                            for retry in range(3):
                                wait = min(60, (2 ** retry) + random.uniform(0, 1))
                                print(f"TheirStack 429, retrying in {wait:.1f}s (attempt {retry + 1})")
                                time.sleep(wait)
                                self._api_calls += 1
                                response = client.post(f"{self.BASE_URL}/jobs/search", headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}, json=payload, timeout=30)
                                if response.status_code != 429:
                                    break
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
                code = e.response.status_code
                if code == 429:
                    print(f"TheirStack rate limit hit after {len(jobs)} jobs.")
                elif not jobs:
                    # Surface plan/auth errors (e.g. 403 E-020 "Premium
                    # functionality limitation") instead of returning an empty
                    # list that the pipeline mislabels as "no_match".
                    body = ""
                    try:
                        body = e.response.text[:300]
                    except Exception:
                        body = ""
                    raise RuntimeError(f"TheirStack HTTP {code}: {body}") from e
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

        # Employment type: TheirStack field is "employment_statuses" (array of: full_time, part_time, contract, etc.)
        from app.services.adapters.base import normalize_employment_type
        emp_statuses = raw_data.get("employment_statuses") or []
        emp_type = normalize_employment_type(emp_statuses[0] if emp_statuses else "")

        return {
            "client_name": raw_data.get("company_name", "Unknown Company"),
            "job_title": raw_data.get("job_title", "Unknown Position"),
            "state": state,
            "posting_date": posting_date,
            "job_link": raw_data.get("url", "") or raw_data.get("job_url", ""),
            "salary_min": float(salary_min) if salary_min else None,
            "salary_max": float(salary_max) if salary_max else None,
            "source": "theirstack",
            "employment_type": emp_type,
            "external_job_id": str(raw_data.get("id", "")) if raw_data.get("id") else "",
            "city": city,
            "employer_linkedin_url": raw_data.get("company_linkedin_url") or "",
            "employer_website": raw_data.get("company_url") or "",
            "job_publisher": "theirstack",
        }
