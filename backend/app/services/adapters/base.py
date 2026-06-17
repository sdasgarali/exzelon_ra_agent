"""Base adapter interfaces for all provider types."""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class RateLimitError(RuntimeError):
    """Raised when an API returns HTTP 429 (rate limit exceeded).

    Carries any partial results collected before the rate limit was hit.
    """

    def __init__(self, message: str = "Rate limit exceeded", partial_results: list = None):
        super().__init__(message)
        self.partial_results = partial_results or []


class CreditsExhaustedError(RuntimeError):
    """Raised when a contact discovery adapter's API credits are exhausted.

    The waterfall loop catches this to skip to the next adapter.
    Apollo's subclass re-raises to stop the entire pipeline.
    """

    def __init__(self, message: str = "API credits exhausted", adapter_name: str = "unknown"):
        super().__init__(message)
        self.adapter_name = adapter_name


class BaseAdapter(ABC):
    """Base class for all adapters."""

    @abstractmethod
    def test_connection(self) -> bool:
        """Test connection to the provider."""
        pass


def normalize_employment_type(raw_value: str) -> str:
    """Normalize employment type from various API formats to standard values.

    Standard values: Full-time, Part-time, Contract, Temporary, Internship, Volunteer
    """
    if not raw_value:
        return ""
    v = raw_value.strip().lower().replace("-", "").replace("_", "").replace(" ", "")
    mapping = {
        "fulltime": "Full-time",
        "full": "Full-time",
        "parttime": "Part-time",
        "part": "Part-time",
        "contract": "Contract",
        "contractor": "Contract",
        "c2c": "Contract",
        "corptocorp": "Contract",
        "temporary": "Temporary",
        "temp": "Temporary",
        "seasonal": "Temporary",
        "internship": "Internship",
        "intern": "Internship",
        "volunteer": "Volunteer",
        "permanent": "Full-time",
        "placement": "Internship",
        "student": "Internship",
        "shiftwork": "Full-time",
        "intermittent": "Part-time",
        "jobsharing": "Part-time",
        "multipleschedules": "Full-time",
    }
    return mapping.get(v, raw_value.strip().title() if raw_value.strip() else "")


class JobSourceAdapter(BaseAdapter):
    """Base adapter for job source providers."""

    @staticmethod
    def filter_excluded(
        job: dict,
        exclude_keywords: list = None,
        exclude_company_keywords: list = None,
        exclude_title_keywords: list = None,
        match_mode: str = "word_boundary",
    ) -> bool:
        """Return True if the job should be EXCLUDED.

        match_mode: "word_boundary" (regex \\b) or "substring" (python `in`)
        """
        import re

        if not job:
            return True

        title = (job.get("job_title") or "").lower()
        company = (job.get("client_name") or "").lower()
        combined = f"{title} {company}"

        def _matches(keyword, text):
            if match_mode == "word_boundary":
                return bool(re.search(r"\b" + re.escape(keyword.lower()) + r"\b", text))
            return keyword.lower() in text

        # General exclusions: match against combined title + company
        if exclude_keywords:
            for kw in exclude_keywords:
                if _matches(kw, combined):
                    return True

        # Company-only exclusions
        if exclude_company_keywords:
            for kw in exclude_company_keywords:
                if _matches(kw, company):
                    return True

        # Title-only exclusions
        if exclude_title_keywords:
            for kw in exclude_title_keywords:
                if _matches(kw, title):
                    return True

        return False

    @staticmethod
    def build_negative_terms(
        exclude_keywords: list = None,
        exclude_title_keywords: list = None,
        max_terms: int = 12,
    ) -> list:
        """Build a de-duplicated, bounded list of keywords to exclude server-side.

        Combines general + title exclusions (company exclusions are too numerous
        and unsupported by job-board query syntax, so they stay client-side).
        Bounded by max_terms to respect API query-length limits.
        """
        terms = []
        seen = set()
        for src in (exclude_keywords or [], exclude_title_keywords or []):
            for kw in src:
                k = (kw or "").strip()
                if not k:
                    continue
                low = k.lower()
                if low in seen:
                    continue
                seen.add(low)
                terms.append(k)
                if len(terms) >= max_terms:
                    return terms
        return terms

    @staticmethod
    def google_negative_suffix(terms: list) -> str:
        """Render terms as a Google-style negative suffix (e.g. ' -intern -"staffing agency"').

        Used by Google-backed sources (JSearch, SerpAPI Google Jobs). Multi-word
        terms are quoted. Returns '' when there are no terms.
        """
        if not terms:
            return ""
        parts = []
        for t in terms:
            t = (t or "").strip()
            if not t:
                continue
            parts.append(f'-"{t}"' if " " in t else f"-{t}")
        return (" " + " ".join(parts)) if parts else ""

    def _negative_terms(self, exclude_keywords: list = None) -> list:
        """Resolve negative terms for this adapter call, honoring the push flag.

        Returns [] when query-side exclusion is disabled (``_push_negatives``
        is set False by the pipeline). Pulls title exclusions from the instance
        attribute set in fetch_from_source.
        """
        if not getattr(self, "_push_negatives", True):
            return []
        return self.build_negative_terms(
            exclude_keywords=exclude_keywords,
            exclude_title_keywords=getattr(self, "_exclude_title", None),
        )

    @abstractmethod
    def fetch_jobs(
        self,
        location: str = "United States",
        posted_within_days: int = 1,
        industries: Optional[List[str]] = None,
        exclude_keywords: Optional[List[str]] = None,
        job_titles: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Fetch job postings from the source.

        Returns list of dicts with keys:
        - client_name: Company name
        - job_title: Job title
        - state: State (2-letter code)
        - posting_date: Date posted
        - job_link: URL to job posting
        - salary_min: Minimum salary (optional)
        - salary_max: Maximum salary (optional)
        """
        pass

    @abstractmethod
    def normalize(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize raw job data to standard format."""
        pass


class LeadSourceAdapter(BaseAdapter):
    """Base adapter for LOB-specific lead sources (non-job-board).

    Unlike JobSourceAdapter which fetches job postings, LeadSourceAdapter
    fetches business/organization records for targeted outreach across
    different Lines of Business (RCM, Software Dev, Digital Marketing, etc.).

    Returns list of dicts with standard keys:
    - client_name: Organization/business name (required)
    - industry: Industry category
    - state: State (2-letter code)
    - city: City name
    - domain: Website domain
    - source: Source identifier (e.g., "npi", "google_business")
    - source_url: URL to source listing
    - metadata: Dict with source-specific data (NPI number, PageSpeed score, etc.)
    """

    @abstractmethod
    def fetch_leads(
        self,
        query: str = "",
        location: str = "United States",
        limit: int = 100,
        **kwargs,
    ) -> List[Dict[str, Any]]:
        """Fetch leads from the source.

        Args:
            query: Search query (industry, specialty, keyword, etc.)
            location: Geographic filter
            limit: Max results to return
            **kwargs: Source-specific parameters

        Returns:
            List of normalized lead dicts.
        """
        pass

    @abstractmethod
    def normalize(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize raw source data to standard lead format."""
        pass

    @property
    def source_name(self) -> str:
        """Return the source identifier for this adapter."""
        return self.__class__.__name__.lower().replace("adapter", "")

    @property
    def api_calls_made(self) -> int:
        """Return count of API calls made in this session."""
        return getattr(self, "_api_calls", 0)


class ContactDiscoveryAdapter(BaseAdapter):
    """Base adapter for contact discovery providers."""

    @abstractmethod
    def search_contacts(
        self,
        company_name: str,
        job_title: Optional[str] = None,
        state: Optional[str] = None,
        titles: Optional[List[str]] = None,
        limit: int = 4,
        domain: Optional[str] = None,
        db: Optional[Session] = None,
        lead_domain: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search for contacts at a company.

        Args:
            company_name: Company name (fuzzy, used as fallback)
            domain: Company website domain (e.g. "cognizant.com") — preferred
                    over company_name for precise matching when available.
            limit: Max contacts to return.
            db: Optional DB session for pre-checking existing contacts
                (used by Apollo to skip already-known people).
            lead_domain: Optional domain for matching existing contacts.

        Returns list of dicts with keys:
        - first_name
        - last_name
        - title
        - email
        - phone (optional)
        - location_state
        """
        pass

    @abstractmethod
    def normalize(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize raw contact data to standard format."""
        pass


class EmailValidationAdapter(BaseAdapter):
    """Base adapter for email validation providers."""

    @abstractmethod
    def validate_email(self, email: str) -> Dict[str, Any]:
        """
        Validate a single email.

        Returns dict with keys:
        - status: valid, invalid, catch_all, unknown
        - sub_status: Provider-specific status
        - raw_response: Full provider response
        """
        pass

    @abstractmethod
    def validate_bulk(self, emails: List[str]) -> List[Dict[str, Any]]:
        """
        Validate multiple emails.

        Returns list of validation results.
        """
        pass


class EmailSendAdapter(BaseAdapter):
    """Base adapter for email sending providers."""

    @abstractmethod
    def send_email(
        self,
        to_email: str,
        subject: str,
        body_html: str,
        body_text: Optional[str] = None,
        from_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Send a single email.

        Returns dict with keys:
        - success: bool
        - message_id: Provider message ID
        - error: Error message if failed
        """
        pass

    @abstractmethod
    def send_bulk(
        self,
        messages: List[Dict[str, Any]],
        rate_limit: int = 30
    ) -> List[Dict[str, Any]]:
        """
        Send multiple emails with rate limiting.

        Returns list of send results.
        """
        pass


class CompanyEnrichmentAdapter(BaseAdapter):
    """Base adapter for company enrichment providers."""

    @abstractmethod
    def enrich_company(
        self,
        company_name: str,
        domain: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Enrich company data.

        Returns dict with keys (all optional except company_name):
        - company_name: str
        - domain: str
        - industry: str
        - employee_count: int
        - revenue: str
        - description: str
        - address: str
        - country: str
        - tech_stack: list
        - founded_year: int
        - raw_response: dict
        """
        pass

    @abstractmethod
    def normalize(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize raw company data to standard format."""
        pass


class AIAdapter(BaseAdapter):
    """Base adapter for AI/LLM providers used for email content generation."""

    # Subclasses set this; used to attribute AI cost to a provider.
    PROVIDER_NAME: str = "ai"

    def _track_ai_cost(self, feature: Optional[str] = None) -> None:
        """Record the cost of the last AI call.

        No-op unless a caller (e.g. get_ai_adapter) attached a `_cost_db`
        session. Reads `self._last_usage` (set by each adapter's _call_api).
        Wrapped defensively so cost tracking can never break a generation.
        """
        db = getattr(self, "_cost_db", None)
        if db is None:
            return
        try:
            usage = getattr(self, "_last_usage", None) or {}
            from app.services.cost_tracker import record_ai_cost
            record_ai_cost(
                db,
                provider=getattr(self, "PROVIDER_NAME", "ai"),
                model=getattr(self, "model", "") or "",
                input_tokens=int(usage.get("input_tokens", 0) or 0),
                output_tokens=int(usage.get("output_tokens", 0) or 0),
                feature=feature or getattr(self, "_cost_feature", None),
                tenant_id=getattr(self, "_cost_tenant_id", None),
            )
        except Exception:
            pass

    def research_company(
        self,
        company_name: str,
        domain: Optional[str] = None,
        location: Optional[str] = None
    ) -> Dict[str, Any]:
        """Research a company using LLM knowledge.

        Returns dict with keys (all optional):
        - website: str
        - industry: str
        - description: str
        - company_size: str
        - headquarters: str
        - founded_year: int
        - employee_count: int
        """
        raise NotImplementedError("research_company not implemented for this adapter")

    @abstractmethod
    def generate_email(
        self,
        contact_name: str,
        contact_title: str,
        company_name: str,
        job_title: str,
        template: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Generate personalized email content.

        Returns dict with keys:
        - subject: Email subject line
        - body_html: HTML email body
        - body_text: Plain text email body
        """
        pass

    @abstractmethod
    def generate_subject_variations(
        self,
        base_subject: str,
        count: int = 3
    ) -> List[str]:
        """
        Generate subject line variations for A/B testing.

        Returns list of subject line strings.
        """
        pass

    @abstractmethod
    def analyze_response(
        self,
        email_content: str,
        response_content: str
    ) -> Dict[str, Any]:
        """
        Analyze an email response to determine intent.

        Returns dict with keys:
        - sentiment: positive, negative, neutral
        - intent: interested, not_interested, question, out_of_office, bounce
        - suggested_action: follow_up, archive, respond, etc.
        """
        pass
