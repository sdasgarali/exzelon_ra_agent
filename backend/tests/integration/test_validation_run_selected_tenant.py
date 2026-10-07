"""POST /pipelines/email-validation/run-selected must run under the caller's tenant.

Regression: tenant_id was not passed, so the JobRun was filed under tenant 1 and
the validation credits were metered against no tenant.
"""
import pytest

from app.db.models.contact import ContactDetails

pytestmark = pytest.mark.integration


def test_run_selected_passes_tenant(client, db_session, sa_headers, test_tenant, monkeypatch):
    captured = {}

    def fake_pipeline(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr("app.services.pipelines.email_validation.run_email_validation_pipeline", fake_pipeline)

    c = ContactDetails(tenant_id=test_tenant.tenant_id, client_name="Acme", first_name="A",
                       last_name="B", email="a.b@acme-example.com")
    db_session.add(c)
    db_session.commit()

    headers = {**sa_headers, "X-Tenant-ID": str(test_tenant.tenant_id)}
    r = client.post("/api/v1/pipelines/email-validation/run-selected", headers=headers,
                    json={"contact_ids": [c.contact_id]})
    assert r.status_code == 200, r.text
    assert captured.get("tenant_id") == test_tenant.tenant_id
    assert captured.get("emails") == ["a.b@acme-example.com"]
