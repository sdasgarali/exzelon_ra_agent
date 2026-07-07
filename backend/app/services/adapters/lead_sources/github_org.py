"""GitHub Organization lead source adapter for Software Dev & AI Services LOBs.

Fetches organization data from GitHub API — repos, languages, activity,
and team size. Useful for finding companies with active development
that may need software dev or AI services.

Free API (unauthenticated: 60 req/hr, authenticated: 5000 req/hr).
No API key required but recommended via GITHUB_TOKEN for higher limits.
"""
import structlog
import requests
from typing import List, Dict, Any, Optional

from app.services.adapters.base import LeadSourceAdapter, RateLimitError

logger = structlog.get_logger()

BASE_URL = "https://api.github.com"


class GitHubOrgAdapter(LeadSourceAdapter):
    """Adapter for GitHub API (free / token-authenticated).

    Searches for organizations by keyword, location, and size.
    Returns org profile, public repo count, languages, and activity signals.
    """

    def __init__(self, token: str = ""):
        self.token = token  # Optional GitHub personal access token
        self._api_calls = 0

    @property
    def _headers(self) -> Dict[str, str]:
        headers = {"Accept": "application/vnd.github+json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def test_connection(self) -> bool:
        try:
            resp = requests.get(f"{BASE_URL}/rate_limit", headers=self._headers, timeout=10)
            self._api_calls += 1
            return resp.status_code == 200
        except Exception:
            return False

    def fetch_leads(
        self,
        query: str = "",
        location: str = "United States",
        limit: int = 30,
        language: str = "",
        min_repos: int = 5,
        min_followers: int = 0,
        **kwargs,
    ) -> List[Dict[str, Any]]:
        """Search GitHub organizations.

        Args:
            query: Keyword search (org name, description)
            location: Location filter
            language: Programming language filter
            min_repos: Minimum public repos
            min_followers: Minimum followers
            limit: Max results (API max 100 per page)
        """
        leads = []

        # Build GitHub search query
        search_parts = []
        if query:
            search_parts.append(query)
        search_parts.append("type:org")

        if location and location != "United States":
            search_parts.append(f"location:{location}")

        if language:
            search_parts.append(f"language:{language}")

        if min_repos:
            search_parts.append(f"repos:>={min_repos}")

        if min_followers:
            search_parts.append(f"followers:>={min_followers}")

        search_q = " ".join(search_parts)
        per_page = min(limit, 30)  # Keep reasonable to avoid rate limits

        try:
            resp = requests.get(
                f"{BASE_URL}/search/users",
                headers=self._headers,
                params={"q": search_q, "per_page": per_page, "sort": "repositories", "order": "desc"},
                timeout=30,
            )
            self._api_calls += 1

            if resp.status_code == 403:
                remaining = resp.headers.get("X-RateLimit-Remaining", "0")
                if remaining == "0":
                    raise RateLimitError("GitHub API rate limit exceeded", partial_results=leads)
            resp.raise_for_status()
            data = resp.json()
        except RateLimitError:
            raise
        except Exception as e:
            logger.error("github_org_search_error", error=str(e))
            return leads

        items = data.get("items") or []

        # Fetch detailed org info for each result
        for item in items:
            login = item.get("login", "")
            if not login:
                continue

            org_detail = self._get_org_detail(login)
            if org_detail:
                normalized = self.normalize(org_detail)
                if normalized:
                    leads.append(normalized)

        logger.info("github_org_fetched", count=len(leads), query=query)
        return leads

    def _get_org_detail(self, login: str) -> Optional[Dict[str, Any]]:
        """Fetch detailed org profile."""
        try:
            resp = requests.get(
                f"{BASE_URL}/orgs/{login}",
                headers=self._headers,
                timeout=15,
            )
            self._api_calls += 1

            if resp.status_code == 403:
                remaining = resp.headers.get("X-RateLimit-Remaining", "0")
                if remaining == "0":
                    raise RateLimitError(f"GitHub rate limit fetching org {login}")
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()
        except RateLimitError:
            raise
        except Exception as e:
            logger.warning("github_org_detail_error", login=login, error=str(e))
            return None

    def normalize(self, raw_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Normalize GitHub org to standard lead format."""
        try:
            name = raw_data.get("name") or raw_data.get("login", "")
            login = raw_data.get("login", "")
            if not name:
                return None

            description = raw_data.get("description", "") or ""
            location = raw_data.get("location", "") or ""
            blog = raw_data.get("blog", "") or ""
            email = raw_data.get("email", "") or ""
            twitter = raw_data.get("twitter_username", "") or ""
            public_repos = raw_data.get("public_repos", 0)
            followers = raw_data.get("followers", 0)
            created_at = raw_data.get("created_at", "")
            company_url = raw_data.get("html_url", "")

            # Parse location into state/city
            state = ""
            city = ""
            if location:
                parts = [p.strip() for p in location.split(",")]
                if len(parts) >= 2:
                    city = parts[0]
                    state = parts[-1]
                elif len(parts) == 1:
                    city = parts[0]

            # Domain from blog URL
            domain = ""
            if blog:
                if not blog.startswith("http"):
                    blog = f"https://{blog}"
                from urllib.parse import urlparse
                parsed = urlparse(blog)
                domain = parsed.netloc.replace("www.", "")

            # Estimate company size from public repos and followers
            estimated_size = _estimate_team_size(public_repos, followers)

            return {
                "client_name": name,
                "industry": "Software & Technology",
                "state": state,
                "city": city,
                "domain": domain,
                "source": "github_org",
                "source_url": company_url,
                "job_title": f"Software Organization ({public_repos} repos)",
                "job_link": company_url,
                "posting_date": None,
                "employer_website": blog or company_url,
                "contact_email": email or None,
                "company_size": estimated_size,
                "metadata": {
                    "github_login": login,
                    "description": description,
                    "public_repos": public_repos,
                    "followers": followers,
                    "location": location,
                    "twitter": twitter,
                    "created_at": created_at,
                    "estimated_team_size": estimated_size,
                },
            }
        except Exception as e:
            logger.warning("github_org_normalize_error", error=str(e))
            return None

    @property
    def source_name(self) -> str:
        return "github_org"


def _estimate_team_size(repos: int, followers: int) -> str:
    """Estimate team size from GitHub activity metrics."""
    activity_score = repos + (followers * 2)
    if activity_score > 1000:
        return "501-1000"
    if activity_score > 500:
        return "201-500"
    if activity_score > 200:
        return "51-200"
    if activity_score > 50:
        return "11-50"
    return "1-10"
