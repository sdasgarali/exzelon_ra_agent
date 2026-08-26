"""GDPR data-subject export + erasure (ELR-024)."""
import pytest

from app.db.models.contact import ContactDetails, OutreachStatus as ContactOutreachStatus
from app.db.models.suppression import SuppressionList

pytestmark = pytest.mark.integration


def _contact(db, tid, email="Jane.Doe@example.com"):
    c = ContactDetails(tenant_id=tid, client_name="Acme", first_name="Jane",
                       last_name="Doe", email=email, phone="+1555", title="VP")
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def test_export_returns_contact_pii(client, db_session, test_tenant, auth_headers):
    _contact(db_session, test_tenant.tenant_id)
    r = client.get("/api/v1/gdpr/export?email=jane.doe@example.com", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert len(body["contacts"]) == 1
    assert body["contacts"][0]["email"].lower() == "jane.doe@example.com"
    assert body["contacts"][0]["phone"] == "+1555"


def test_erase_anonymises_and_suppresses(client, db_session, test_tenant, auth_headers):
    c = _contact(db_session, test_tenant.tenant_id, email="erase.me@example.com")
    r = client.post("/api/v1/gdpr/erase", json={"email": "erase.me@example.com"},
                    headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["erased"] == 1

    db_session.expire_all()
    c2 = db_session.query(ContactDetails).get(c.contact_id)
    assert c2.first_name == "REDACTED"
    assert c2.last_name is None and c2.phone is None
    assert "gdpr.invalid" in c2.email  # original PII email scrubbed
    assert c2.outreach_status == ContactOutreachStatus.UNSUBSCRIBED
    # original address suppressed
    assert db_session.query(SuppressionList).filter(
        SuppressionList.email == "erase.me@example.com",
        SuppressionList.tenant_id == test_tenant.tenant_id,
    ).count() == 1


def test_erase_requires_tenant_for_super_admin(client, sa_headers):
    # ELR-005/023: erasure is a write → super-admin must impersonate.
    r = client.post("/api/v1/gdpr/erase", json={"email": "x@y.com"}, headers=sa_headers)
    assert r.status_code == 400


def test_export_does_not_leak_across_tenants(client, db_session, test_tenant, auth_headers):
    # A contact in ANOTHER tenant must not appear in this tenant's export.
    from app.db.models.tenant import Tenant, TenantPlan
    other = Tenant(name="Other", slug="gdpr-other", plan=TenantPlan.ENTERPRISE)
    db_session.add(other)
    db_session.commit()
    _contact(db_session, other.tenant_id, email="shared@example.com")
    r = client.get("/api/v1/gdpr/export?email=shared@example.com", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["contacts"] == []  # belongs to the other tenant
