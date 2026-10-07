"""POST /saved-searches/{id}/execute: tenant-scoped and no longer crashing.

Regressions: the natural-language path searched every tenant's leads (tenant_id not
passed), and the filter path used non-existent LeadDetails.status / company_name (500).
"""
import json
from datetime import date

import pytest

from app.core.security import create_access_token, get_password_hash
from app.db.models.lead import LeadDetails, LeadStatus
from app.db.models.saved_search import SavedSearch
from app.db.models.tenant import Tenant, TenantPlan
from app.db.models.user import User, UserRole

pytestmark = pytest.mark.integration


def _lead(db, tenant_id, company, state="TX"):
    lead = LeadDetails(tenant_id=tenant_id, client_name=company, job_title="Nurse Manager", state=state,
                       posting_date=date.today(), source="linkedin", lead_status=LeadStatus.NEW,
                       industry="Healthcare")
    db.add(lead)
    return lead


@pytest.fixture
def two_tenants(db_session, test_tenant, admin_user):
    other = Tenant(name="Other", slug="other-ss", plan=TenantPlan.ENTERPRISE)
    db_session.add(other)
    db_session.flush()
    _lead(db_session, test_tenant.tenant_id, "Mine Hospital")
    _lead(db_session, other.tenant_id, "Theirs Hospital")
    db_session.commit()
    return test_tenant, other


def _search(db, tenant, user, filters):
    s = SavedSearch(tenant_id=tenant.tenant_id, user_id=user.user_id, name="s",
                    filters_json=json.dumps(filters), is_shared=False)
    db.add(s)
    db.commit()
    return s


def test_nl_saved_search_stays_in_tenant(client, db_session, auth_headers, admin_user, two_tenants):
    mine, _ = two_tenants
    s = _search(db_session, mine, admin_user, {"query": "nurse manager jobs in Texas"})
    r = client.post(f"/api/v1/saved-searches/{s.search_id}/execute", headers=auth_headers)
    assert r.status_code == 200, r.text
    names = {row["company_name"] for row in r.json()["results"]}
    assert names == {"Mine Hospital"}


def test_filter_saved_search_with_status_works(client, db_session, auth_headers, admin_user, two_tenants):
    mine, _ = two_tenants
    s = _search(db_session, mine, admin_user, {"state": "TX", "status": "new"})
    r = client.post(f"/api/v1/saved-searches/{s.search_id}/execute", headers=auth_headers)
    assert r.status_code == 200, r.text
    rows = r.json()["results"]
    assert [row["company_name"] for row in rows] == ["Mine Hospital"]
    assert rows[0]["status"] == "new"


def test_read_key_may_execute(client, db_session, auth_headers, admin_user, two_tenants):
    mine, _ = two_tenants
    s = _search(db_session, mine, admin_user, {"state": "TX"})
    key = client.post("/api/v1/integrations/api-keys", headers=auth_headers,
                      json={"name": "r", "scopes": ["read"]}).json()["key"]
    r = client.post(f"/api/v1/saved-searches/{s.search_id}/execute", headers={"X-API-Key": key})
    assert r.status_code == 200, r.text
