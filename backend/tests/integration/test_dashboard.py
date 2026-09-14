"""Integration tests for dashboard endpoints."""
import pytest
from datetime import date, datetime, timedelta

from app.api.endpoints.dashboard import _kpi_cache
from app.core.security import create_access_token, get_password_hash
from app.db.models.contact import ContactDetails
from app.db.models.outreach import OutreachChannel, OutreachEvent, OutreachStatus
from app.db.models.tenant import Tenant, TenantPlan
from app.db.models.user import User, UserRole

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _clear_kpi_cache():
    """/dashboard/kpis memoises into a module-level dict for 60s, keyed by
    tenant+dates. Every test here runs as tenant 1 with default dates, so without
    this the second test in the file would read the first one's response."""
    _kpi_cache.update({"data": None, "expires": 0, "key": ""})
    yield
    _kpi_cache.update({"data": None, "expires": 0, "key": ""})


@pytest.fixture
def other_tenant(db_session):
    """A second tenant, for cross-tenant leak regressions."""
    tenant = Tenant(
        name="Other Org", slug="other-org", plan=TenantPlan.ENTERPRISE,
        max_users=999, max_mailboxes=999, max_contacts=999999,
        max_campaigns=999, max_leads=999999,
    )
    db_session.add(tenant)
    db_session.commit()
    db_session.refresh(tenant)
    return tenant


@pytest.fixture
def other_tenant_headers(db_session, other_tenant):
    user = User(
        email="admin@other-org.com", password_hash=get_password_hash("testpassword"),
        full_name="Other Admin", role=UserRole.ADMIN,
        is_active=True, is_verified=True, tenant_id=other_tenant.tenant_id,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    token = create_access_token(data={
        "sub": user.email, "role": user.role,
        "tenant_id": user.tenant_id, "plan": "enterprise",
    })
    return {"Authorization": f"Bearer {token}"}


def _make_contacts(db_session, tenant_id, specs):
    """Create contacts as (slug, validation_status) pairs."""
    created = []
    for slug, status in specs:
        contact = ContactDetails(
            tenant_id=tenant_id,
            client_name=f"{slug.title()} Corp",
            first_name=slug.title(),
            last_name="Tester",
            email=f"{slug}-{tenant_id}@example.com",
            validation_status=status,
        )
        db_session.add(contact)
        created.append(contact)
    db_session.commit()
    for contact in created:
        db_session.refresh(contact)
    return created


def _make_outreach(db_session, tenant_id, sent=0, replied=0):
    """Attach `sent`/`replied` outreach events to one contact of this tenant."""
    contact = _make_contacts(db_session, tenant_id, [(f"outreach{tenant_id}", "valid")])[0]
    for status, count in ((OutreachStatus.SENT, sent), (OutreachStatus.REPLIED, replied)):
        for _ in range(count):
            db_session.add(OutreachEvent(
                tenant_id=tenant_id,
                contact_id=contact.contact_id,
                channel=OutreachChannel.SMTP,
                status=status,
                sent_at=datetime.utcnow(),
            ))
    db_session.commit()
    return contact


class TestDashboardEndpoints:
    """Tests for /api/v1/dashboard endpoints."""

    def test_get_kpis(self, client, auth_headers):
        """Test getting KPIs returns expected structure."""
        response = client.get("/api/v1/dashboard/kpis", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "period" in data
        assert "total_leads" in data
        assert "total_contacts" in data
        assert "emails_sent" in data
        assert "bounce_rate_percent" in data
        assert "reply_rate_percent" in data

    def test_get_kpis_with_date_range(self, client, auth_headers):
        """Test KPIs with explicit date range."""
        today = date.today()
        from_str = (today - timedelta(days=7)).isoformat()
        to_str = today.isoformat()
        response = client.get(
            f"/api/v1/dashboard/kpis?from_date={from_str}&to_date={to_str}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["period"]["from"] == from_str
        assert data["period"]["to"] == to_str

    def test_get_leads_sourced(self, client, auth_headers, sample_lead):
        """Test leads-sourced tab returns a list."""
        response = client.get("/api/v1/dashboard/leads-sourced", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_get_contacts_identified(self, client, auth_headers):
        """Test contacts-identified tab returns a list."""
        response = client.get(
            "/api/v1/dashboard/contacts-identified", headers=auth_headers
        )
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_get_outreach_sent(self, client, auth_headers):
        """Test outreach-sent tab returns a list."""
        response = client.get("/api/v1/dashboard/outreach-sent", headers=auth_headers)
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_get_client_categories(self, client, auth_headers):
        """Test client-categories tab returns summary and clients."""
        response = client.get(
            "/api/v1/dashboard/client-categories", headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "summary" in data
        assert "clients" in data

    def test_get_trends(self, client, auth_headers):
        """Test trends endpoint returns daily data."""
        response = client.get("/api/v1/dashboard/trends", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "daily_leads" in data
        assert "daily_outreach" in data

    def test_get_stats(self, client, auth_headers, sample_lead):
        """Test consolidated stats endpoint."""
        response = client.get("/api/v1/dashboard/stats", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "leads" in data
        assert data["leads"]["total"] >= 1
        assert "by_status" in data["leads"]
        assert "by_source" in data["leads"]
        assert "contacts" in data
        assert "outreach" in data
        assert "mailboxes" in data
        assert "templates" in data


class TestDashboardKpiAccuracy:
    """Regressions for the 'Valid Emails / Emails Sent show 0' report.

    Two defects were behind it:
      1. total_valid_emails counted a date-windowed slice of `email_validation_results`
         (a provider-response log with no tenant_id that is never restamped on
         re-validation), so it decayed to 0 while contacts stayed marked valid.
      2. /stats and /trends never tenant-scoped outreach_events, so their charts
         contradicted the tenant-scoped KPI tiles.
    """

    def test_valid_emails_counts_contacts_not_validation_log(
        self, client, auth_headers, db_session, test_tenant
    ):
        """total_valid_emails must track ContactDetails.validation_status.

        The old implementation read `email_validation_results`; with none of those rows
        present this returned 0 even though valid contacts existed.
        """
        _make_contacts(
            db_session, test_tenant.tenant_id,
            [("a", "valid"), ("b", "valid"), ("c", "invalid"), ("d", None)],
        )

        data = client.get("/api/v1/dashboard/kpis", headers=auth_headers).json()
        assert data["total_valid_emails"] == 2
        assert data["total_contacts"] == 4

    def test_valid_emails_matches_stats_validation_breakdown(
        self, client, auth_headers, db_session, test_tenant
    ):
        """The tile and the validation donut render on the same screen from two
        endpoints — they must agree, which is the user-visible symptom."""
        _make_contacts(
            db_session, test_tenant.tenant_id,
            [("a", "valid"), ("b", "valid"), ("c", "invalid")],
        )

        kpis = client.get("/api/v1/dashboard/kpis", headers=auth_headers).json()
        stats = client.get("/api/v1/dashboard/stats", headers=auth_headers).json()

        donut_valid = sum(
            count
            for name, count in stats["contacts"]["by_validation_status"].items()
            if name.lower() == "valid"
        )
        assert kpis["total_valid_emails"] == donut_valid == 2

    def test_valid_emails_is_case_insensitive(
        self, client, auth_headers, db_session, test_tenant
    ):
        """validation_status is a free-form String(50); the model documents
        capitalised values while every writer emits lowercase."""
        _make_contacts(
            db_session, test_tenant.tenant_id, [("a", "Valid"), ("b", "valid")]
        )

        data = client.get("/api/v1/dashboard/kpis", headers=auth_headers).json()
        assert data["total_valid_emails"] == 2

    def test_valid_emails_is_tenant_scoped(
        self, client, auth_headers, db_session, test_tenant, other_tenant_headers,
        other_tenant,
    ):
        """The old source table had no tenant_id at all, so this count leaked."""
        _make_contacts(db_session, test_tenant.tenant_id, [("a", "valid"), ("b", "valid")])
        _make_contacts(db_session, other_tenant.tenant_id, [("x", "valid")])

        mine = client.get("/api/v1/dashboard/kpis", headers=auth_headers).json()
        theirs = client.get("/api/v1/dashboard/kpis", headers=other_tenant_headers).json()

        assert mine["total_valid_emails"] == 2
        assert theirs["total_valid_emails"] == 1

    def test_stats_outreach_is_tenant_scoped(
        self, client, auth_headers, db_session, test_tenant, other_tenant_headers,
        other_tenant,
    ):
        """/stats fed the Outreach Outcomes chart with every tenant's events."""
        _make_outreach(db_session, test_tenant.tenant_id, sent=3, replied=1)
        _make_outreach(db_session, other_tenant.tenant_id, sent=7, replied=2)

        mine = client.get("/api/v1/dashboard/stats", headers=auth_headers).json()
        theirs = client.get("/api/v1/dashboard/stats", headers=other_tenant_headers).json()

        assert mine["outreach"]["total_sent"] == 3
        assert mine["outreach"]["total_replied"] == 1
        assert theirs["outreach"]["total_sent"] == 7
        assert theirs["outreach"]["total_replied"] == 2

    def test_trends_outreach_is_tenant_scoped(
        self, client, auth_headers, db_session, test_tenant, other_tenant_headers,
        other_tenant,
    ):
        """daily_outreach was unfiltered while daily_leads beside it was scoped."""
        _make_outreach(db_session, test_tenant.tenant_id, sent=2)
        _make_outreach(db_session, other_tenant.tenant_id, sent=5)

        mine = client.get("/api/v1/dashboard/trends", headers=auth_headers).json()
        theirs = client.get("/api/v1/dashboard/trends", headers=other_tenant_headers).json()

        assert sum(d["count"] for d in mine["daily_outreach"]) == 2
        assert sum(d["count"] for d in theirs["daily_outreach"]) == 5

    def test_kpis_still_exposes_emails_replied_key(self, client, auth_headers):
        """The funnel's Replied step read `total_replied`, a key this payload has
        never contained. Pin the contract so the frontend key stays correct."""
        data = client.get("/api/v1/dashboard/kpis", headers=auth_headers).json()
        assert "emails_replied" in data
        assert "total_replied" not in data
