"""Tenant isolation on /validation/* (MCP phase 2, agent B2).

Regressions covered:
- /validation/validate-bulk and /validate-pending-contacts did not pass tenant_id to
  the pipeline: the JobRun went to tenant 1 and credits were metered to no tenant.
- /validation/results, /results/{email} and /stats/summary were global.
  ``email_validation_results`` has no tenant_id, so a tenant sees only results for
  emails of its own contacts (case-insensitive). A super admin with no tenant
  selected keeps the global view.
- The pipeline wrote validation_status onto every tenant's contacts that shared an
  email address.
"""
import pytest

from app.db.models.contact import ContactDetails
from app.db.models.email_validation import EmailValidationResult, ValidationStatus
from app.db.models.job_run import JobRun
from app.db.models.tenant import Tenant, TenantPlan
from app.services.pipelines import email_validation as ev_pipeline

pytestmark = pytest.mark.integration

API = "/api/v1"


@pytest.fixture
def other_tenant(db_session):
    t = Tenant(name="B", slug="tenant-b", plan=TenantPlan.ENTERPRISE, max_users=9,
               max_mailboxes=9, max_contacts=999, max_campaigns=9, max_leads=999)
    db_session.add(t)
    db_session.commit()
    db_session.refresh(t)
    return t


def _contact(db, tenant_id, email, validation_status=None):
    c = ContactDetails(tenant_id=tenant_id, client_name="Acme", first_name="Pat",
                       last_name="Lee", email=email, validation_status=validation_status)
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def _result(db, email, status=ValidationStatus.VALID):
    r = EmailValidationResult(email=email, provider="mock", status=status)
    db.add(r)
    db.commit()
    return r


@pytest.fixture
def two_tenant_results(db_session, test_tenant, other_tenant):
    # Tenant A's contact uses mixed case — the scope must match lower(email).
    _contact(db_session, test_tenant.tenant_id, "Pat@Client-A.com")
    _contact(db_session, other_tenant.tenant_id, "pat@client-b.com")
    _result(db_session, "pat@client-a.com", ValidationStatus.VALID)
    _result(db_session, "pat@client-b.com", ValidationStatus.INVALID)
    _result(db_session, "orphan@nowhere.com", ValidationStatus.INVALID)


# ---------------------------------------------------------------------------
# Pipelines receive the tenant
# ---------------------------------------------------------------------------

def test_validate_bulk_passes_tenant(client, auth_headers, test_tenant, monkeypatch):
    captured = {}
    monkeypatch.setattr(ev_pipeline, "run_email_validation_pipeline",
                        lambda **kw: captured.update(kw))
    r = client.post(f"{API}/validation/validate-bulk", headers=auth_headers,
                    json={"emails": ["x@acme-example.com"]})
    assert r.status_code == 200, r.text
    assert captured.get("tenant_id") == test_tenant.tenant_id
    assert captured.get("emails") == ["x@acme-example.com"]


def test_validate_pending_contacts_passes_tenant(
    client, auth_headers, db_session, test_tenant, other_tenant, monkeypatch,
):
    _contact(db_session, test_tenant.tenant_id, "a@client-a.com")
    _contact(db_session, other_tenant.tenant_id, "b@client-b.com")
    captured = {}
    monkeypatch.setattr(ev_pipeline, "run_email_validation_pipeline",
                        lambda **kw: captured.update(kw))
    r = client.post(f"{API}/validation/validate-pending-contacts", headers=auth_headers)
    assert r.status_code == 200, r.text
    assert captured.get("tenant_id") == test_tenant.tenant_id
    assert captured.get("emails") == ["a@client-a.com"]


# ---------------------------------------------------------------------------
# Reads are scoped
# ---------------------------------------------------------------------------

def test_results_list_scoped_to_tenant(client, auth_headers, two_tenant_results):
    r = client.get(f"{API}/validation/results", headers=auth_headers)
    assert r.status_code == 200, r.text
    assert [x["email"] for x in r.json()] == ["pat@client-a.com"]


def test_results_list_super_admin_global(client, sa_headers, two_tenant_results):
    r = client.get(f"{API}/validation/results", headers=sa_headers)
    assert r.status_code == 200, r.text
    assert len(r.json()) == 3


def test_results_list_super_admin_impersonating(client, sa_headers, other_tenant,
                                                two_tenant_results):
    headers = {**sa_headers, "X-Tenant-ID": str(other_tenant.tenant_id)}
    r = client.get(f"{API}/validation/results", headers=headers)
    assert r.status_code == 200, r.text
    assert [x["email"] for x in r.json()] == ["pat@client-b.com"]


def test_result_by_email_scoped(client, auth_headers, two_tenant_results):
    own = client.get(f"{API}/validation/results/PAT@client-a.com", headers=auth_headers)
    assert own.status_code == 200, own.text
    foreign = client.get(f"{API}/validation/results/pat@client-b.com", headers=auth_headers)
    assert foreign.status_code == 404
    orphan = client.get(f"{API}/validation/results/orphan@nowhere.com", headers=auth_headers)
    assert orphan.status_code == 404


def test_stats_scoped(client, auth_headers, sa_headers, two_tenant_results):
    mine = client.get(f"{API}/validation/stats/summary", headers=auth_headers).json()
    assert mine["total_validated"] == 1
    assert mine["estimated_bounce_rate"] == 0
    everyone = client.get(f"{API}/validation/stats/summary", headers=sa_headers).json()
    assert everyone["total_validated"] == 3


# ---------------------------------------------------------------------------
# Pipeline writes stay inside the tenant
# ---------------------------------------------------------------------------

def test_pipeline_updates_only_own_contacts_and_files_run_under_tenant(
    db_session, test_tenant, other_tenant, monkeypatch,
):
    monkeypatch.setattr(db_session, "close", lambda: None)
    monkeypatch.setattr(ev_pipeline, "SessionLocal", lambda: db_session)
    ca = _contact(db_session, test_tenant.tenant_id, "shared@client.com")
    cb = _contact(db_session, other_tenant.tenant_id, "shared@client.com")

    ev_pipeline.run_email_validation_pipeline(
        emails=["shared@client.com"], provider="mock", triggered_by="t",
        tenant_id=test_tenant.tenant_id,
    )
    db_session.expire_all()
    assert db_session.get(ContactDetails, ca.contact_id).validation_status is not None
    assert db_session.get(ContactDetails, cb.contact_id).validation_status is None
    run = db_session.query(JobRun).filter(JobRun.pipeline_name == "email_validation").one()
    assert run.tenant_id == test_tenant.tenant_id
