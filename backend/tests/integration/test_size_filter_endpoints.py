"""Integration tests for numeric operator-based company-size filtering
on the leads and clients list endpoints."""
import pytest
from datetime import date

from app.db.models.lead import LeadDetails, LeadStatus
from app.db.models.client import ClientInfo, ClientStatus

pytestmark = pytest.mark.integration


def _mk_lead(db, tenant_id, name, size, **extra):
    lead = LeadDetails(
        tenant_id=tenant_id,
        client_name=name,
        job_title="Analyst",
        state="CA",
        posting_date=date.today(),
        job_link=f"https://jobs.example.com/{name}",
        source="linkedin",
        lead_status=LeadStatus.NEW,
        company_size=size,
        is_archived=False,
        **extra,
    )
    db.add(lead)
    return lead


def _mk_client(db, tenant_id, name, size=None, employee_count=None):
    c = ClientInfo(
        tenant_id=tenant_id,
        client_name=name,
        status=ClientStatus.ACTIVE,
        company_size=size,
        employee_count=employee_count,
        is_archived=False,
    )
    db.add(c)
    return c


def _names(data):
    return {item["client_name"] for item in data["items"]}


class TestLeadsSizeFilter:
    @pytest.fixture(autouse=True)
    def seed(self, db_session, test_tenant):
        t = test_tenant.tenant_id
        _mk_lead(db_session, t, "Micro", "10")
        _mk_lead(db_session, t, "Mid", "150")
        _mk_lead(db_session, t, "BandLow", "51-200")   # parses to 51 (lower bound)
        _mk_lead(db_session, t, "Big", "300")
        _mk_lead(db_session, t, "BlankSize", "")        # unknown
        _mk_lead(db_session, t, "NoSize", None)         # unknown
        db_session.commit()

    def test_greater_than(self, client, auth_headers):
        r = client.get("/api/v1/leads?company_size_op=gt&company_size_value=200", headers=auth_headers)
        assert r.status_code == 200
        assert _names(r.json()) == {"Big"}

    def test_less_than_uses_band_lower_bound(self, client, auth_headers):
        r = client.get("/api/v1/leads?company_size_op=lt&company_size_value=50", headers=auth_headers)
        assert _names(r.json()) == {"Micro"}  # BandLow=51 is NOT < 50

    def test_between_inclusive(self, client, auth_headers):
        r = client.get("/api/v1/leads?company_size_op=between&company_size_value=100&company_size_value2=200", headers=auth_headers)
        assert _names(r.json()) == {"Mid"}

    def test_equals(self, client, auth_headers):
        r = client.get("/api/v1/leads?company_size_op=eq&company_size_value=150", headers=auth_headers)
        assert _names(r.json()) == {"Mid"}

    def test_not_equal_excludes_unknown(self, client, auth_headers):
        r = client.get("/api/v1/leads?company_size_op=ne&company_size_value=150", headers=auth_headers)
        # 10, 51, 300 match; blank/None (unknown) are excluded
        assert _names(r.json()) == {"Micro", "BandLow", "Big"}

    def test_include_unknown_toggle(self, client, auth_headers):
        r = client.get(
            "/api/v1/leads?company_size_op=gt&company_size_value=200&company_size_include_unknown=true",
            headers=auth_headers,
        )
        assert _names(r.json()) == {"Big", "BlankSize", "NoSize"}


class TestLeadsSizeClientFallback:
    """A lead with no own size defers to its client's authoritative size."""

    @pytest.fixture(autouse=True)
    def seed(self, db_session, test_tenant):
        t = test_tenant.tenant_id
        _mk_client(db_session, t, "BigCo", employee_count=500)
        _mk_client(db_session, t, "SmallCo", employee_count=10)
        _mk_lead(db_session, t, "BigCo", None)     # size from client (500)
        _mk_lead(db_session, t, "SmallCo", None)   # size from client (10)
        db_session.commit()

    def test_client_fallback_matches(self, client, auth_headers):
        r = client.get("/api/v1/leads?company_size_op=gt&company_size_value=200", headers=auth_headers)
        assert _names(r.json()) == {"BigCo"}

    def test_client_known_size_excluded_from_unknown_bucket(self, client, auth_headers):
        # include_unknown must NOT re-add leads whose client has a known size
        r = client.get(
            "/api/v1/leads?company_size_op=gt&company_size_value=200&company_size_include_unknown=true",
            headers=auth_headers,
        )
        assert _names(r.json()) == {"BigCo"}


class TestClientsSizeFilter:
    @pytest.fixture(autouse=True)
    def seed(self, db_session, test_tenant):
        t = test_tenant.tenant_id
        _mk_client(db_session, t, "MicroClient", size="10")
        _mk_client(db_session, t, "MidClient", size="150")
        _mk_client(db_session, t, "BandClient", size="51-200")       # 51
        _mk_client(db_session, t, "CountClient", employee_count=250) # employee_count wins
        _mk_client(db_session, t, "UnknownClient", size=None)
        db_session.commit()

    def test_greater_than(self, client, auth_headers):
        r = client.get("/api/v1/clients?company_size_op=gt&company_size_value=200", headers=auth_headers)
        assert r.status_code == 200
        assert _names(r.json()) == {"CountClient"}

    def test_between(self, client, auth_headers):
        r = client.get("/api/v1/clients?company_size_op=between&company_size_value=50&company_size_value2=200", headers=auth_headers)
        assert _names(r.json()) == {"MidClient", "BandClient"}

    def test_at_most(self, client, auth_headers):
        r = client.get("/api/v1/clients?company_size_op=lte&company_size_value=51", headers=auth_headers)
        assert _names(r.json()) == {"MicroClient", "BandClient"}

    def test_include_unknown(self, client, auth_headers):
        r = client.get(
            "/api/v1/clients?company_size_op=gt&company_size_value=200&company_size_include_unknown=true",
            headers=auth_headers,
        )
        assert _names(r.json()) == {"CountClient", "UnknownClient"}

    def test_no_filter_returns_all(self, client, auth_headers):
        r = client.get("/api/v1/clients", headers=auth_headers)
        assert r.status_code == 200
        assert len(r.json()["items"]) == 5
