"""PageSpeed Insights lead source adapter for Digital Marketing LOB.

Fetches website performance data from Google PageSpeed Insights API.
Free API, no key required (but key recommended for higher rate limits).
Useful for finding businesses with poorly performing websites that need
digital marketing / web optimization services.

API docs: https://developers.google.com/speed/docs/insights/v5/get-started
"""
import structlog
import requests
from typing import List, Dict, Any, Optional

from app.services.adapters.base import LeadSourceAdapter, RateLimitError

logger = structlog.get_logger()

BASE_URL = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"


class PageSpeedAdapter(LeadSourceAdapter):
    """Adapter for Google PageSpeed Insights API (free).

    Analyzes website performance and returns scores for performance,
    accessibility, best practices, and SEO. Low-scoring sites are
    strong prospects for digital marketing services.
    """

    def __init__(self, api_key: str = ""):
        self.api_key = api_key  # Optional but recommended for rate limits
        self._api_calls = 0

    def test_connection(self) -> bool:
        try:
            params = {"url": "https://example.com", "strategy": "mobile"}
            if self.api_key:
                params["key"] = self.api_key
            resp = requests.get(BASE_URL, params=params, timeout=30)
            self._api_calls += 1
            return resp.status_code == 200
        except Exception:
            return False

    def fetch_leads(
        self,
        query: str = "",
        location: str = "United States",
        limit: int = 20,
        domains: Optional[List[str]] = None,
        strategy: str = "mobile",
        max_score: float = 0.5,
        **kwargs,
    ) -> List[Dict[str, Any]]:
        """Audit websites and return those with low performance scores.

        Args:
            domains: List of domains to audit (required)
            strategy: "mobile" or "desktop"
            max_score: Only return sites scoring below this (0.0-1.0)
            limit: Max results
        """
        if not domains:
            logger.warning("pagespeed_no_domains", msg="Provide domains list to audit")
            return []

        leads = []
        for domain in domains[:limit]:
            url = domain if domain.startswith("http") else f"https://{domain}"
            result = self._audit_url(url, strategy)
            if result:
                # Only include sites with low scores (potential prospects)
                perf_score = result.get("metadata", {}).get("performance_score", 1.0)
                if perf_score <= max_score:
                    leads.append(result)

        logger.info("pagespeed_fetched", count=len(leads), total_audited=len(domains))
        return leads

    def _audit_url(self, url: str, strategy: str = "mobile") -> Optional[Dict[str, Any]]:
        """Audit a single URL."""
        params = {
            "url": url,
            "strategy": strategy,
            "category": ["performance", "accessibility", "best-practices", "seo"],
        }
        if self.api_key:
            params["key"] = self.api_key

        try:
            resp = requests.get(BASE_URL, params=params, timeout=60)
            self._api_calls += 1

            if resp.status_code == 429:
                raise RateLimitError(f"PageSpeed rate limit for {url}")
            resp.raise_for_status()
            data = resp.json()
        except RateLimitError:
            raise
        except Exception as e:
            logger.warning("pagespeed_audit_error", url=url, error=str(e))
            return None

        return self.normalize({"url": url, "data": data})

    def normalize(self, raw_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Normalize PageSpeed result to standard lead format."""
        try:
            url = raw_data.get("url", "")
            data = raw_data.get("data", {})

            lighthouse = data.get("lighthouseResult", {})
            categories = lighthouse.get("categories", {})

            # Extract scores (0.0 to 1.0)
            performance = categories.get("performance", {}).get("score", 0)
            accessibility = categories.get("accessibility", {}).get("score", 0)
            best_practices = categories.get("best-practices", {}).get("score", 0)
            seo = categories.get("seo", {}).get("score", 0)

            # Extract key metrics
            audits = lighthouse.get("audits", {})
            fcp = audits.get("first-contentful-paint", {}).get("numericValue", 0)  # ms
            lcp = audits.get("largest-contentful-paint", {}).get("numericValue", 0)
            cls = audits.get("cumulative-layout-shift", {}).get("numericValue", 0)
            tbt = audits.get("total-blocking-time", {}).get("numericValue", 0)
            speed_index = audits.get("speed-index", {}).get("numericValue", 0)

            # Extract domain
            from urllib.parse import urlparse
            parsed = urlparse(url)
            domain = parsed.netloc.replace("www.", "")
            company_name = domain.split(".")[0].title() if domain else ""

            # Overall score (average of all categories)
            avg_score = (
                (performance or 0) + (accessibility or 0) +
                (best_practices or 0) + (seo or 0)
            ) / 4

            # Generate issue summary
            issues = []
            if performance and performance < 0.5:
                issues.append("slow performance")
            if accessibility and accessibility < 0.7:
                issues.append("poor accessibility")
            if seo and seo < 0.7:
                issues.append("weak SEO")
            if best_practices and best_practices < 0.7:
                issues.append("outdated best practices")

            issue_text = ", ".join(issues) if issues else "website needs optimization"

            return {
                "client_name": company_name,
                "industry": "Digital Presence",
                "state": "",
                "city": "",
                "domain": domain,
                "source": "pagespeed",
                "source_url": f"https://pagespeed.web.dev/analysis?url={url}",
                "job_title": f"Website Issues: {issue_text}",
                "job_link": url,
                "posting_date": None,
                "employer_website": url,
                "metadata": {
                    "performance_score": performance,
                    "accessibility_score": accessibility,
                    "best_practices_score": best_practices,
                    "seo_score": seo,
                    "average_score": round(avg_score, 2),
                    "fcp_ms": round(fcp),
                    "lcp_ms": round(lcp),
                    "cls": round(cls, 3),
                    "tbt_ms": round(tbt),
                    "speed_index_ms": round(speed_index),
                    "issues": issues,
                    "strategy": raw_data.get("strategy", "mobile"),
                },
            }
        except Exception as e:
            logger.warning("pagespeed_normalize_error", error=str(e))
            return None

    def audit_domains(
        self, domains: List[str], strategy: str = "mobile"
    ) -> List[Dict[str, Any]]:
        """Convenience method: audit multiple domains and return all results.

        Unlike fetch_leads, this returns ALL results regardless of score.
        """
        results = []
        for domain in domains:
            url = domain if domain.startswith("http") else f"https://{domain}"
            result = self._audit_url(url, strategy)
            if result:
                results.append(result)
        return results

    @property
    def source_name(self) -> str:
        return "pagespeed"
