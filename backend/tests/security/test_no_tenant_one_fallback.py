"""No code path may fall back to tenant 1 when the tenant is unknown (ELR-005).

`tenant_id or 1` silently filed a super admin's un-impersonated writes, pipeline runs
and Resource Pool events under tenant 1, a real customer workspace, and read tenant 1's
company exclusions for runs that had no tenant. These tests pin the replacement
behaviour: refuse (400 / ValueError), or ignore, but never borrow tenant 1.
"""
import hashlib
import hmac
import json

import pytest

from app.core.settings_resolver import set_tenant_setting
from app.db.models.cost_tracking import CostEntry
from app.db.models.resource_pool_attribution import ResourcePoolAttribution
from app.db.models.tenant import Tenant, TenantPlan

pytestmark = pytest.mark.security


# --- HTTP endpoints: super admin without a selected tenant -------------------------

def test_templates_list_requires_a_tenant_for_unscoped_super_admin(client, super_admin_headers):
    r = client.get("/api/v1/templates", headers=super_admin_headers)
    assert r.status_code == 400
    assert "Select a tenant" in r.json()["detail"]


def test_active_template_requires_a_tenant_for_unscoped_super_admin(client, super_admin_headers):
    r = client.get("/api/v1/templates/active", headers=super_admin_headers)
    assert r.status_code == 400


def test_templates_list_still_works_for_a_tenant_admin(client, auth_headers):
    assert client.get("/api/v1/templates", headers=auth_headers).status_code == 200


def test_manual_cost_entry_requires_a_tenant(client, db_session, super_admin_headers):
    before = db_session.query(CostEntry).count()
    r = client.post("/api/v1/analytics/costs", headers=super_admin_headers,
                    json={"category": "other", "amount": 5, "entry_date": "2026-11-01"})
    assert r.status_code == 400, r.text
    assert db_session.query(CostEntry).count() == before


# --- Pipelines: refuse to run without a tenant -------------------------------------

def test_lead_sourcing_pipeline_requires_tenant():
    from app.services.pipelines.lead_sourcing import run_lead_sourcing_pipeline
    with pytest.raises(ValueError, match="tenant_id is required"):
        run_lead_sourcing_pipeline(sources=["auto"], triggered_by="test", tenant_id=None)


def test_lead_import_requires_tenant(tmp_path):
    from app.services.pipelines.lead_sourcing import import_leads_from_file
    with pytest.raises(ValueError, match="tenant_id is required"):
        import_leads_from_file(str(tmp_path / "x.xlsx"), triggered_by="test", tenant_id=None)


def test_upsert_client_requires_tenant(db_session):
    from app.services.pipelines.lead_sourcing import upsert_client
    with pytest.raises(ValueError, match="tenant_id is required"):
        upsert_client(db_session, "Acme Mfg", tenant_id=None)


def test_contact_enrichment_pipeline_requires_tenant():
    from app.services.pipelines.contact_enrichment import run_contact_enrichment_pipeline
    with pytest.raises(ValueError, match="tenant_id is required"):
        run_contact_enrichment_pipeline(triggered_by="test", tenant_id=None)


# --- Eligibility: no tenant means no (borrowed) exclusion list ---------------------

def test_eligibility_without_tenant_does_not_read_tenant_one_exclusions(db_session):
    from app.db.models.company_exclusion import CompanyExclusion, normalize_company_for_exclusion
    from app.services.lead_eligibility import LeadEligibilityGate

    t1 = db_session.get(Tenant, 1) or Tenant(tenant_id=1, name="One", slug="one", plan=TenantPlan.FREE)
    db_session.add(t1)
    db_session.commit()
    db_session.add(CompanyExclusion(
        tenant_id=1, company_name="Tenant One Secret Client",
        company_name_normalized=normalize_company_for_exclusion("Tenant One Secret Client"),
        is_active=True,
    ))
    db_session.commit()

    gate = LeadEligibilityGate(db_session, tenant_id=None)
    global_set, by_lob, _ = gate._load_company_exclusions()
    assert global_set == set()
    assert by_lob == {}


# --- Resource Pool webhook: an event we can't attribute is ignored -----------------

SECRET = "whsec_test_secret"


def _sign(body: str) -> str:
    return hmac.new(SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()


def test_resource_pool_event_without_tenant_is_ignored_not_filed_under_tenant_one(client, db_session):
    set_tenant_setting(db_session, "resourcepool_webhook_secret", SECRET, tenant_id=None)
    db_session.commit()
    body = json.dumps({"event": "placement.created", "createdAt": "2026-11-06T00:00:00Z",
                       "data": {"externalRef": "ra-lead-999999", "placementId": "plc_orphan"}})
    r = client.post("/api/v1/integrations/resource-pool/webhook", content=body,
                    headers={"X-Exzelon-Signature": _sign(body)})
    assert r.status_code == 200
    assert r.json().get("ignored") == "unknown_tenant"
    assert db_session.query(ResourcePoolAttribution).filter(
        ResourcePoolAttribution.rp_entity_id == "plc_orphan").count() == 0


# --- Scheduler: a failed tenant lookup must not turn into "run everything as tenant 1" ---

def test_scheduler_tenant_lookup_failure_runs_no_tenant(monkeypatch):
    from app.services.warmup import scheduler

    class _BrokenSession:
        def query(self, *a, **k):
            raise RuntimeError("db down")

        def close(self):
            pass

    monkeypatch.setattr(scheduler, "_get_db", lambda: _BrokenSession())
    assert scheduler._get_active_tenant_ids() == []


# --- System log rows: NULL tenant, hidden from every tenant -------------------------

def test_system_automation_event_has_no_tenant_and_is_hidden_from_tenants(db_session, test_tenant):
    from app.db.models.automation_event import AutomationEvent
    from app.db.query_helpers import tenant_filter
    from app.services.automation_logger import log_automation_event

    log_automation_event(db_session, "scheduler_run", "Platform job ran", tenant_id=None)
    row = db_session.query(AutomationEvent).filter(AutomationEvent.title == "Platform job ran").one()
    assert row.tenant_id is None

    seen_by_tenant = tenant_filter(db_session.query(AutomationEvent), AutomationEvent,
                                   test_tenant.tenant_id).filter(
        AutomationEvent.title == "Platform job ran").count()
    seen_by_super_admin = tenant_filter(db_session.query(AutomationEvent), AutomationEvent,
                                        None).filter(
        AutomationEvent.title == "Platform job ran").count()
    assert seen_by_tenant == 0
    assert seen_by_super_admin == 1


def test_system_ai_cost_is_recorded_without_a_tenant(db_session):
    from app.services.cost_tracker import record_ai_cost

    record_ai_cost(db_session, provider="openai", model="gpt-4o-mini", input_tokens=100,
                   output_tokens=50, feature="test-system-cost", tenant_id=None)
    db_session.commit()
    row = db_session.query(CostEntry).filter(CostEntry.notes.like("%test-system-cost%")).one()
    assert row.tenant_id is None


# --- CRM sync: always one workspace ------------------------------------------------

def test_crm_sync_functions_require_a_tenant(db_session):
    from app.services import crm_sync_engine as eng
    for fn in (lambda: eng.sync_contacts_from_crm("hubspot", db_session),
               lambda: eng.sync_deals_to_crm("hubspot", db_session),
               lambda: eng.run_crm_sync(db_session)):
        with pytest.raises(ValueError, match="tenant_id is required"):
            fn()


def test_crm_deal_push_only_sends_the_tenants_own_deals(db_session, test_tenant, monkeypatch):
    from app.db.models.crm_sync_log import CRMSyncLog
    from app.db.models.deal import Deal, DealStage
    from app.services import crm_sync_engine as eng

    other = Tenant(name="Other Co", slug="other-co-crm", plan=TenantPlan.FREE)
    db_session.add(other)
    db_session.commit()
    stages = {}
    for t in (test_tenant.tenant_id, other.tenant_id):
        st = DealStage(tenant_id=t, name="Open", stage_order=1)
        db_session.add(st)
        db_session.commit()
        stages[t] = st.stage_id
    db_session.add(Deal(tenant_id=test_tenant.tenant_id, name="Mine", stage_id=stages[test_tenant.tenant_id]))
    db_session.add(Deal(tenant_id=other.tenant_id, name="Not mine", stage_id=stages[other.tenant_id]))
    db_session.commit()

    pushed = []
    monkeypatch.setattr(eng, "_push_deal_to_hubspot", lambda data, db: pushed.append(data["name"]))
    eng.sync_deals_to_crm("hubspot", db_session, tenant_id=test_tenant.tenant_id)

    assert pushed == ["Mine"]
    log = db_session.query(CRMSyncLog).order_by(CRMSyncLog.sync_id.desc()).first()
    assert log.tenant_id == test_tenant.tenant_id


def test_crm_sync_endpoint_requires_a_tenant(client, super_admin_headers):
    r = client.post("/api/v1/crm-sync/run", headers=super_admin_headers, json={"crm_type": "hubspot"})
    assert r.status_code == 400
