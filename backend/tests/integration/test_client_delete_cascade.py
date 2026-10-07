"""DELETE /clients/{id}: archives the client and its own tenant's contacts only.

Regression: the cascade filtered on a non-existent ContactDetails.company_name,
so every single-client delete returned 500; it also had no tenant filter.
"""
import pytest

from app.db.models.client import ClientInfo
from app.db.models.contact import ContactDetails
from app.db.models.tenant import Tenant, TenantPlan

pytestmark = pytest.mark.integration


def _contact(db, tenant_id, email):
    c = ContactDetails(tenant_id=tenant_id, client_name="Acme Corp",
                       first_name="A", last_name="B", email=email)
    db.add(c)
    return c


def test_delete_client_archives_own_tenant_contacts_only(client, db_session, auth_headers, test_tenant):
    other = Tenant(name="Other Org", slug="other-org", plan=TenantPlan.ENTERPRISE)
    db_session.add(other)
    db_session.commit()

    acme = ClientInfo(tenant_id=test_tenant.tenant_id, client_name="Acme Corp")
    db_session.add(acme)
    mine = _contact(db_session, test_tenant.tenant_id, "a@acme.com")
    theirs = _contact(db_session, other.tenant_id, "b@acme.com")
    db_session.commit()

    r = client.delete(f"/api/v1/clients/{acme.client_id}", headers=auth_headers)
    assert r.status_code == 204, r.text

    db_session.expire_all()
    assert db_session.get(ClientInfo, acme.client_id).is_archived is True
    assert db_session.get(ContactDetails, mine.contact_id).is_archived is True
    assert db_session.get(ContactDetails, theirs.contact_id).is_archived is False
