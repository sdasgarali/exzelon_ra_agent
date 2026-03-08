"""Base adapter interfaces for all provider types."""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional


class RateLimitError(RuntimeError):
    """Raised when an API returns HTTP 429 (rate limit exceeded).

    Carries any partial results collected before the rate limit was hit.
    """

    def __init__(self, message: str = "Rate limit exceeded", partial_results: list = None):
        super().__init__(message)
        self.partial_results = partial_results or []


class BaseAdapter(ABC):
    """Base class for all adapters."""

    @abstractmethod
    def test_connection(self) -> bool:
        """Test connection to the provider."""
        pass


class JobSourceAdapter(BaseAdapter):
    """Base adapter for job source providers."""

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


class ContactDiscoveryAdapter(BaseAdapter):
    """Base adapter for contact discovery providers."""

    @abstractmethod
    def search_contacts(
        self,
        company_name: str,
        job_title: Optional[str] = None,
        state: Optional[str] = None,
        titles: Optional[List[str]] = None,
        limit: int = 4
    ) -> List[Dict[str, Any]]:
        """
        Search for contacts at a company.

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
