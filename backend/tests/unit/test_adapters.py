"""Unit tests for provider adapters."""
import pytest
from datetime import date
from app.services.adapters.job_sources.mock import MockJobSourceAdapter
from app.services.adapters.contact_discovery.mock import MockContactDiscoveryAdapter
from app.services.adapters.email_validation.mock import MockEmailValidationAdapter
from app.services.adapters.email_sending.mock import MockEmailSendAdapter
from app.db.models.email_validation import ValidationStatus
from app.db.models.contact import PriorityLevel

# New adapters
from app.services.adapters.job_sources.theirstack import TheirStackAdapter
from app.services.adapters.job_sources.serpapi import SerpAPIAdapter
from app.services.adapters.job_sources.adzuna import AdzunaAdapter
from app.services.adapters.contact_discovery.hunter_contact import HunterContactAdapter
from app.services.adapters.contact_discovery.snovio import SnovioAdapter
from app.services.adapters.contact_discovery.rocketreach import RocketReachAdapter
from app.services.adapters.contact_discovery.pdl import PDLAdapter
from app.services.adapters.contact_discovery.proxycurl import ProxycurlAdapter
from app.services.adapters.company.clearbit import ClearbitAdapter
from app.services.adapters.company.opencorporates import OpenCorporatesAdapter


class TestMockJobSourceAdapter:
    """Tests for MockJobSourceAdapter."""

    def test_test_connection(self):
        """Test connection should always succeed for mock."""
        adapter = MockJobSourceAdapter()
        assert adapter.test_connection() is True

    def test_fetch_jobs_returns_list(self):
        """Fetch jobs should return a list."""
        adapter = MockJobSourceAdapter()
        jobs = adapter.fetch_jobs()
        assert isinstance(jobs, list)
        assert len(jobs) > 0

    def test_fetch_jobs_with_filters(self):
        """Fetch jobs with exclude keywords should filter results."""
        adapter = MockJobSourceAdapter()
        jobs = adapter.fetch_jobs(exclude_keywords=["IT", "Software"])
        for job in jobs:
            assert "IT" not in job["job_title"].upper()
            assert "Software" not in job["job_title"]

    def test_job_has_required_fields(self):
        """Each job should have required fields."""
        adapter = MockJobSourceAdapter()
        jobs = adapter.fetch_jobs()
        required_fields = ["client_name", "job_title", "state", "posting_date", "source"]
        for job in jobs:
            for field in required_fields:
                assert field in job

    def test_normalize_passthrough(self):
        """Normalize should return the same data for mock."""
        adapter = MockJobSourceAdapter()
        data = {"test": "value"}
        assert adapter.normalize(data) == data


class TestMockContactDiscoveryAdapter:
    """Tests for MockContactDiscoveryAdapter."""

    def test_test_connection(self):
        """Test connection should always succeed for mock."""
        adapter = MockContactDiscoveryAdapter()
        assert adapter.test_connection() is True

    def test_search_contacts_returns_list(self):
        """Search contacts should return a list."""
        adapter = MockContactDiscoveryAdapter()
        contacts = adapter.search_contacts(company_name="Test Company")
        assert isinstance(contacts, list)
        assert len(contacts) > 0

    def test_search_contacts_respects_limit(self):
        """Search contacts should respect the limit parameter."""
        adapter = MockContactDiscoveryAdapter()
        contacts = adapter.search_contacts(company_name="Test Company", limit=2)
        assert len(contacts) <= 2

    def test_contact_has_required_fields(self):
        """Each contact should have required fields."""
        adapter = MockContactDiscoveryAdapter()
        contacts = adapter.search_contacts(company_name="Test Company")
        required_fields = ["first_name", "last_name", "email", "priority_level"]
        for contact in contacts:
            for field in required_fields:
                assert field in contact

    def test_contact_email_format(self):
        """Contact email should have valid format."""
        adapter = MockContactDiscoveryAdapter()
        contacts = adapter.search_contacts(company_name="Test Company")
        for contact in contacts:
            assert "@" in contact["email"]
            assert "." in contact["email"]


class TestMockEmailValidationAdapter:
    """Tests for MockEmailValidationAdapter."""

    def test_test_connection(self):
        """Test connection should always succeed for mock."""
        adapter = MockEmailValidationAdapter()
        assert adapter.test_connection() is True

    def test_validate_email_returns_result(self):
        """Validate email should return a result dict."""
        adapter = MockEmailValidationAdapter()
        result = adapter.validate_email("test@example.com")
        assert isinstance(result, dict)
        assert "email" in result
        assert "status" in result

    def test_validate_email_normalizes_email(self):
        """Validate email should lowercase the email."""
        adapter = MockEmailValidationAdapter()
        result = adapter.validate_email("TEST@EXAMPLE.COM")
        assert result["email"] == "test@example.com"

    def test_validate_email_returns_valid_status(self):
        """Validate email should return a valid ValidationStatus."""
        adapter = MockEmailValidationAdapter()
        result = adapter.validate_email("test@example.com")
        assert result["status"] in [
            ValidationStatus.VALID,
            ValidationStatus.INVALID,
            ValidationStatus.CATCH_ALL,
            ValidationStatus.UNKNOWN
        ]

    def test_validate_bulk_returns_list(self):
        """Validate bulk should return a list of results."""
        adapter = MockEmailValidationAdapter()
        emails = ["test1@example.com", "test2@example.com", "test3@example.com"]
        results = adapter.validate_bulk(emails)
        assert isinstance(results, list)
        assert len(results) == len(emails)


class TestMockEmailSendAdapter:
    """Tests for MockEmailSendAdapter."""

    def test_test_connection(self):
        """Test connection should always succeed for mock."""
        adapter = MockEmailSendAdapter()
        assert adapter.test_connection() is True

    def test_send_email_success(self):
        """Send email should return success."""
        adapter = MockEmailSendAdapter()
        result = adapter.send_email(
            to_email="test@example.com",
            subject="Test Subject",
            body_html="<p>Test body</p>"
        )
        assert result["success"] is True
        assert result["message_id"] is not None
        assert result["error"] is None

    def test_send_email_stores_email(self):
        """Send email should store the sent email."""
        adapter = MockEmailSendAdapter()
        adapter.clear_sent_emails()
        adapter.send_email(
            to_email="test@example.com",
            subject="Test Subject",
            body_html="<p>Test body</p>"
        )
        sent_emails = adapter.get_sent_emails()
        assert len(sent_emails) == 1
        assert sent_emails[0]["to"] == "test@example.com"

    def test_send_bulk_respects_rate_limit(self):
        """Send bulk should process all messages."""
        adapter = MockEmailSendAdapter()
        messages = [
            {"to_email": f"test{i}@example.com", "subject": f"Test {i}", "body_html": "<p>Body</p>"}
            for i in range(3)
        ]
        results = adapter.send_bulk(messages, rate_limit=100)  # High rate for fast test
        assert len(results) == 3
        assert all(r["success"] for r in results)


# ═══════════════════════════════════════════════════════════════════════
# NEW JOB SOURCE ADAPTERS
# ═══════════════════════════════════════════════════════════════════════

class TestTheirStackAdapter:
    """Tests for TheirStackAdapter."""

    def test_no_api_key_test_connection_returns_false(self):
        """test_connection returns False when no API key."""
        adapter = TheirStackAdapter(api_key="")
        assert adapter.test_connection() is False

    def test_fetch_jobs_raises_without_api_key(self):
        """fetch_jobs raises ValueError when no API key."""
        adapter = TheirStackAdapter(api_key="")
        with pytest.raises(ValueError, match="API key"):
            adapter.fetch_jobs()

    def test_normalize_basic(self):
        """normalize produces standard job dict."""
        adapter = TheirStackAdapter(api_key="test")
        raw = {
            "id": "ts-123",
            "company_name": "Acme Corp",
            "job_title": "HR Manager",
            "job_location": "Austin, TX",
            "date_posted": "2026-03-01T10:30:00Z",
            "url": "https://example.com/job/123",
            "min_annual_salary": 50000,
            "max_annual_salary": 70000,
            "company_linkedin_url": "https://linkedin.com/company/acme",
            "company_url": "https://acme.com",
        }
        result = adapter.normalize(raw)
        assert result["client_name"] == "Acme Corp"
        assert result["job_title"] == "HR Manager"
        assert result["source"] == "theirstack"
        assert result["external_job_id"] == "ts-123"
        assert isinstance(result["posting_date"], date)

    def test_normalize_handles_missing_fields(self):
        """normalize handles missing optional fields."""
        adapter = TheirStackAdapter(api_key="test")
        raw = {
            "company_name": "Test Co",
            "job_title": "Manager",
            "job_location": "Unknown",
            "date_posted": "2026-01-01",
        }
        result = adapter.normalize(raw)
        assert result["client_name"] == "Test Co"
        assert result["source"] == "theirstack"

    def test_normalize_returns_none_for_none_input(self):
        """normalize returns None for None input."""
        adapter = TheirStackAdapter(api_key="test")
        assert adapter.normalize(None) is None


class TestSerpAPIAdapter:
    """Tests for SerpAPIAdapter."""

    def test_no_api_key_test_connection_returns_false(self):
        """test_connection returns False when no API key."""
        adapter = SerpAPIAdapter(api_key="")
        assert adapter.test_connection() is False

    def test_fetch_jobs_raises_without_api_key(self):
        """fetch_jobs raises ValueError when no API key."""
        adapter = SerpAPIAdapter(api_key="")
        with pytest.raises(ValueError, match="API key"):
            adapter.fetch_jobs()

    def test_normalize_basic(self):
        """normalize produces standard job dict from Google Jobs data."""
        adapter = SerpAPIAdapter(api_key="test")
        raw = {
            "job_id": "gj-456",
            "company_name": "Tech Corp",
            "title": "Operations Manager",
            "location": "San Francisco, CA",
            "detected_extensions": {
                "posted_at": "3 days ago",
                "salary": "$60,000-$80,000",
            },
            "apply_options": [{"link": "https://example.com/apply"}],
        }
        result = adapter.normalize(raw)
        assert result["client_name"] == "Tech Corp"
        assert result["job_title"] == "Operations Manager"
        assert result["source"] == "serpapi"
        assert result["job_publisher"] == "google_jobs"
        assert isinstance(result["posting_date"], date)

    def test_normalize_returns_none_for_none_input(self):
        """normalize returns None for None input."""
        adapter = SerpAPIAdapter(api_key="test")
        assert adapter.normalize(None) is None

    def test_normalize_handles_missing_extensions(self):
        """normalize handles missing detected_extensions."""
        adapter = SerpAPIAdapter(api_key="test")
        raw = {
            "company_name": "Basic Corp",
            "title": "Manager",
            "location": "NY",
        }
        result = adapter.normalize(raw)
        assert result["client_name"] == "Basic Corp"
        assert result["source"] == "serpapi"


class TestAdzunaAdapter:
    """Tests for AdzunaAdapter."""

    def test_no_credentials_test_connection_returns_false(self):
        """test_connection returns False when no credentials."""
        adapter = AdzunaAdapter(app_id="", api_key="")
        assert adapter.test_connection() is False

    def test_fetch_jobs_raises_without_credentials(self):
        """fetch_jobs raises ValueError when credentials missing."""
        adapter = AdzunaAdapter(app_id="", api_key="")
        with pytest.raises(ValueError):
            adapter.fetch_jobs()

    def test_normalize_basic(self):
        """normalize produces standard job dict from Adzuna data."""
        adapter = AdzunaAdapter(app_id="test", api_key="test")
        raw = {
            "id": "az-789",
            "title": "Warehouse Manager",
            "created": "2026-02-28T15:00:00Z",
            "location": {
                "display_name": "Chicago, IL",
                "area": ["US", "IL", "Chicago"],
            },
            "company": {"display_name": "Logistics Inc"},
            "salary_min": 45000,
            "salary_max": 65000,
            "redirect_url": "https://adzuna.com/job/789",
        }
        result = adapter.normalize(raw)
        assert result["client_name"] == "Logistics Inc"
        assert result["job_title"] == "Warehouse Manager"
        assert result["source"] == "adzuna"
        assert result["state"] == "IL"
        assert result["city"] == "Chicago"
        assert isinstance(result["posting_date"], date)

    def test_normalize_returns_none_for_none_input(self):
        """normalize returns None for None input."""
        adapter = AdzunaAdapter(app_id="test", api_key="test")
        assert adapter.normalize(None) is None

    def test_normalize_handles_missing_company(self):
        """normalize handles missing company field."""
        adapter = AdzunaAdapter(app_id="test", api_key="test")
        raw = {
            "id": "az-101",
            "title": "Manager",
            "created": "2026-01-01",
            "location": {"display_name": "Dallas, TX"},
        }
        result = adapter.normalize(raw)
        assert result["source"] == "adzuna"
        assert result["job_title"] == "Manager"


# ═══════════════════════════════════════════════════════════════════════
# NEW CONTACT DISCOVERY ADAPTERS
# ═══════════════════════════════════════════════════════════════════════

class TestHunterContactAdapter:
    """Tests for HunterContactAdapter."""

    def test_no_api_key_test_connection_returns_false(self):
        """test_connection returns False when no API key."""
        adapter = HunterContactAdapter(api_key="")
        assert adapter.test_connection() is False

    def test_search_contacts_raises_without_api_key(self):
        """search_contacts raises ValueError when no API key."""
        adapter = HunterContactAdapter(api_key="")
        with pytest.raises(ValueError, match="API key"):
            adapter.search_contacts(company_name="Test Co")

    def test_normalize_basic(self):
        """normalize produces standard contact dict."""
        adapter = HunterContactAdapter(api_key="test")
        raw = {
            "value": "john@acme.com",
            "first_name": "John",
            "last_name": "Smith",
            "position": "HR Manager",
            "phone_number": "+1-555-0123",
        }
        result = adapter.normalize(raw)
        assert result["first_name"] == "John"
        assert result["last_name"] == "Smith"
        assert result["email"] == "john@acme.com"
        assert result["title"] == "HR Manager"
        assert result["source"] == "hunter_contact"
        assert isinstance(result["priority_level"], PriorityLevel)

    def test_normalize_returns_none_for_missing_email(self):
        """normalize returns None when no email in data."""
        adapter = HunterContactAdapter(api_key="test")
        raw = {"first_name": "John", "last_name": "Smith"}
        result = adapter.normalize(raw)
        assert result is None

    def test_normalize_returns_none_for_none_input(self):
        """normalize returns None for None input."""
        adapter = HunterContactAdapter(api_key="test")
        assert adapter.normalize(None) is None

    def test_priority_p1_hiring_manager(self):
        """Hiring Manager title gets P1 priority."""
        adapter = HunterContactAdapter(api_key="test")
        priority = adapter._determine_priority("Hiring Manager")
        assert priority == PriorityLevel.P1_JOB_POSTER

    def test_priority_p5_default(self):
        """Unknown title gets P5 priority."""
        adapter = HunterContactAdapter(api_key="test")
        priority = adapter._determine_priority("Chief Widget Officer")
        assert priority == PriorityLevel.P5_FUNCTIONAL_MANAGER


class TestSnovioAdapter:
    """Tests for SnovioAdapter."""

    def test_no_credentials_test_connection_returns_false(self):
        """test_connection returns False when no credentials."""
        adapter = SnovioAdapter(client_id="", client_secret="")
        assert adapter.test_connection() is False

    def test_search_contacts_raises_without_credentials(self):
        """search_contacts raises ValueError when credentials missing."""
        adapter = SnovioAdapter(client_id="", client_secret="")
        with pytest.raises(ValueError):
            adapter.search_contacts(company_name="Test Co")

    def test_normalize_basic(self):
        """normalize produces standard contact dict."""
        adapter = SnovioAdapter(client_id="test", client_secret="test")
        raw = {
            "email": "jane@acme.com",
            "firstName": "Jane",
            "lastName": "Doe",
            "position": "Recruiter",
        }
        result = adapter.normalize(raw)
        assert result["first_name"] == "Jane"
        assert result["last_name"] == "Doe"
        assert result["email"] == "jane@acme.com"
        assert result["source"] == "snovio"
        assert isinstance(result["priority_level"], PriorityLevel)

    def test_normalize_returns_none_for_missing_email(self):
        """normalize returns None when no email."""
        adapter = SnovioAdapter(client_id="test", client_secret="test")
        raw = {"firstName": "Jane", "lastName": "Doe"}
        result = adapter.normalize(raw)
        assert result is None

    def test_normalize_returns_none_for_none_input(self):
        """normalize returns None for None input."""
        adapter = SnovioAdapter(client_id="test", client_secret="test")
        assert adapter.normalize(None) is None


class TestRocketReachAdapter:
    """Tests for RocketReachAdapter."""

    def test_no_api_key_test_connection_returns_false(self):
        """test_connection returns False when no API key."""
        adapter = RocketReachAdapter(api_key="")
        assert adapter.test_connection() is False

    def test_search_contacts_raises_without_api_key(self):
        """search_contacts raises ValueError when no API key."""
        adapter = RocketReachAdapter(api_key="")
        with pytest.raises(ValueError, match="API key"):
            adapter.search_contacts(company_name="Test Co")

    def test_normalize_basic(self):
        """normalize produces standard contact dict."""
        adapter = RocketReachAdapter(api_key="test")
        raw = {
            "first_name": "Alice",
            "last_name": "Johnson",
            "current_title": "HR Director",
            "current_work_email": "alice@acme.com",
            "phones": [{"number": "+1-555-9876"}],
            "location": "New York, NY",
        }
        result = adapter.normalize(raw)
        assert result["first_name"] == "Alice"
        assert result["last_name"] == "Johnson"
        assert result["email"] == "alice@acme.com"
        assert result["title"] == "HR Director"
        assert result["source"] == "rocketreach"
        assert isinstance(result["priority_level"], PriorityLevel)

    def test_normalize_email_fallback(self):
        """normalize falls back to emails list when current_work_email missing."""
        adapter = RocketReachAdapter(api_key="test")
        raw = {
            "first_name": "Bob",
            "last_name": "Lee",
            "current_title": "Manager",
            "emails": ["bob@work.com", "bob@personal.com"],
        }
        result = adapter.normalize(raw)
        assert result["email"] == "bob@work.com"

    def test_normalize_returns_none_for_no_email(self):
        """normalize returns None when no email at all."""
        adapter = RocketReachAdapter(api_key="test")
        raw = {"first_name": "Empty", "last_name": "User", "current_title": "None"}
        result = adapter.normalize(raw)
        assert result is None

    def test_normalize_returns_none_for_none_input(self):
        """normalize returns None for None input."""
        adapter = RocketReachAdapter(api_key="test")
        assert adapter.normalize(None) is None


class TestPDLAdapter:
    """Tests for PDLAdapter (People Data Labs)."""

    def test_no_api_key_test_connection_returns_false(self):
        """test_connection returns False when no API key."""
        adapter = PDLAdapter(api_key="")
        assert adapter.test_connection() is False

    def test_search_contacts_raises_without_api_key(self):
        """search_contacts raises ValueError when no API key."""
        adapter = PDLAdapter(api_key="")
        with pytest.raises(ValueError, match="API key"):
            adapter.search_contacts(company_name="Test Co")

    def test_normalize_basic(self):
        """normalize produces standard contact dict."""
        adapter = PDLAdapter(api_key="test")
        raw = {
            "first_name": "Robert",
            "last_name": "Brown",
            "job_title": "Operations Manager",
            "work_email": "robert@acme.com",
            "location_region": "CA",
            "phone_numbers": ["+1-555-1234"],
        }
        result = adapter.normalize(raw)
        assert result["first_name"] == "Robert"
        assert result["last_name"] == "Brown"
        assert result["email"] == "robert@acme.com"
        assert result["title"] == "Operations Manager"
        assert result["source"] == "pdl"
        assert result["location_state"] == "CA"
        assert isinstance(result["priority_level"], PriorityLevel)

    def test_normalize_email_from_emails_list(self):
        """normalize extracts email from emails list when work_email missing."""
        adapter = PDLAdapter(api_key="test")
        raw = {
            "first_name": "Test",
            "last_name": "User",
            "job_title": "Manager",
            "emails": [
                {"type": "current_professional", "address": "test@work.com"},
            ],
        }
        result = adapter.normalize(raw)
        assert result["email"] == "test@work.com"

    def test_normalize_returns_none_for_none_input(self):
        """normalize returns None for None input."""
        adapter = PDLAdapter(api_key="test")
        assert adapter.normalize(None) is None


class TestProxycurlAdapter:
    """Tests for ProxycurlAdapter."""

    def test_no_api_key_test_connection_returns_false(self):
        """test_connection returns False when no API key."""
        adapter = ProxycurlAdapter(api_key="")
        assert adapter.test_connection() is False

    def test_search_contacts_raises_without_api_key(self):
        """search_contacts raises ValueError when no API key."""
        adapter = ProxycurlAdapter(api_key="")
        with pytest.raises(ValueError, match="API key"):
            adapter.search_contacts(company_name="Test Co")

    def test_normalize_basic(self):
        """normalize produces standard contact dict."""
        adapter = ProxycurlAdapter(api_key="test")
        raw = {
            "first_name": "Sarah",
            "last_name": "Miller",
            "headline": "HR Manager at Acme Corp",
            "personal_email": "sarah@example.com",
            "experiences": [{"title": "HR Manager", "company": "Acme Corp"}],
            "city": "Boston",
            "state": "Massachusetts",
            "phone_numbers": ["+1-555-4321"],
        }
        result = adapter.normalize(raw)
        assert result["first_name"] == "Sarah"
        assert result["last_name"] == "Miller"
        assert result["email"] == "sarah@example.com"
        assert result["source"] == "proxycurl"
        assert isinstance(result["priority_level"], PriorityLevel)

    def test_normalize_splits_full_name(self):
        """normalize splits full_name when first/last missing."""
        adapter = ProxycurlAdapter(api_key="test")
        raw = {
            "full_name": "John Doe",
            "personal_email": "john@example.com",
            "headline": "Manager",
        }
        result = adapter.normalize(raw)
        assert result["first_name"] == "John"
        assert result["last_name"] == "Doe"

    def test_normalize_returns_none_for_none_input(self):
        """normalize returns None for None input."""
        adapter = ProxycurlAdapter(api_key="test")
        assert adapter.normalize(None) is None


# ═══════════════════════════════════════════════════════════════════════
# COMPANY ENRICHMENT ADAPTERS
# ═══════════════════════════════════════════════════════════════════════

class TestClearbitAdapter:
    """Tests for ClearbitAdapter."""

    def test_no_api_key_test_connection_returns_false(self):
        """test_connection returns False when no API key."""
        adapter = ClearbitAdapter(api_key="")
        assert adapter.test_connection() is False

    def test_enrich_company_raises_without_api_key(self):
        """enrich_company raises ValueError when no API key."""
        adapter = ClearbitAdapter(api_key="")
        with pytest.raises(ValueError, match="API key"):
            adapter.enrich_company(company_name="Test Co")

    def test_normalize_basic(self):
        """normalize produces standard company enrichment dict."""
        adapter = ClearbitAdapter(api_key="test")
        raw = {
            "name": "Acme Corporation",
            "domain": "acme.com",
            "industry": "Technology",
            "category": {"industry": "Software"},
            "metrics": {
                "employees": 250,
                "employeesRange": "200-500",
                "estimatedAnnualRevenue": 50000000,
            },
            "description": "A tech company",
            "geo": {
                "city": "San Francisco",
                "state": "CA",
                "country": "US",
            },
            "tech": ["React", "Node.js"],
            "foundedYear": 2015,
            "logo": "https://logo.clearbit.com/acme.com",
            "linkedin": {"handle": "acme-corporation"},
        }
        result = adapter.normalize(raw)
        assert result["company_name"] == "Acme Corporation"
        assert result["domain"] == "acme.com"
        assert result["found"] is True
        assert result["founded_year"] == 2015
        assert "React" in result["tech_stack"]

    def test_normalize_returns_none_for_none_input(self):
        """normalize returns None for None input."""
        adapter = ClearbitAdapter(api_key="test")
        assert adapter.normalize(None) is None


class TestOpenCorporatesAdapter:
    """Tests for OpenCorporatesAdapter."""

    def test_no_api_key_test_connection_returns_false(self):
        """test_connection returns False when no API key."""
        adapter = OpenCorporatesAdapter(api_key="")
        assert adapter.test_connection() is False

    def test_enrich_company_raises_without_api_key(self):
        """enrich_company raises ValueError when no API key."""
        adapter = OpenCorporatesAdapter(api_key="")
        with pytest.raises(ValueError, match="API key"):
            adapter.enrich_company(company_name="Test Co")

    def test_normalize_basic(self):
        """normalize produces standard company enrichment dict."""
        adapter = OpenCorporatesAdapter(api_key="test")
        raw = {
            "name": "Acme Inc",
            "company_number": "12345678",
            "jurisdiction_code": "us_ca",
            "company_type": "Limited Liability Company",
            "current_status": "Active",
            "incorporation_date": "2015-03-10",
            "registered_address_in_full": "123 Main St, San Francisco, CA 94107",
            "industry_codes": [{"description": "Software Publishing"}],
            "officers": [
                {"officer": {"name": "John Doe", "position": "Director"}},
            ],
        }
        result = adapter.normalize(raw)
        assert result["company_name"] == "Acme Inc"
        assert result["found"] is True
        assert result["company_number"] == "12345678"
        assert result["status"] == "Active"
        assert result["founded_year"] == 2015
        assert len(result["officers"]) == 1

    def test_normalize_returns_none_for_none_input(self):
        """normalize returns None for None input."""
        adapter = OpenCorporatesAdapter(api_key="test")
        assert adapter.normalize(None) is None
