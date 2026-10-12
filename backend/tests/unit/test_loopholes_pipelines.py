"""Regression tests for the credit / tenant-isolation loopholes in the data pipelines
(Plan_Credit_Loopholes.md, Agent A: items A1-A6).

Each test pins one loophole closed:
  A1  contact reuse / sibling auto-enrich / auto-enrich-new-leads never cross tenants
  A2  enrichment bills only NEWLY discovered contacts, never cache reuse
  A3  one bad row undoes only itself (SAVEPOINT), so stored rows == counted == billed
  A4  rows committed at checkpoints are billed even when the run later crashes,
      and nothing is billed twice
  A5  leads created by an intent signal are billed as `lead_sourced`
  A6  company research (LLM) is billed per call, results for gate-dropped companies
      are cached, and permanently-null optional fields don't trigger re-research
"""
from unittest.mock import MagicMock

import pytest
from sqlalchemy import func

from app.core.credit_costs import cost_for
from app.db.models.client import ClientInfo, ClientStatus
from app.db.models.contact import ContactDetails
from app.db.models.credit_usage import CreditUsage
from app.db.models.email_validation import EmailValidationResult, ValidationStatus
from app.db.models.lead import LeadDetails, LeadStatus
from app.db.models.lead_contact import LeadContactAssociation
from app.db.models.line_of_business import LineOfBusiness, LOBType
from app.db.models.tenant import Tenant, TenantPlan
from app.services import company_enrichment, intent_signal_monitor
from app.services.pipelines import contact_enrichment, email_validation, lead_sourcing

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _tenant(db, slug):
    t = Tenant(name=slug.title(), slug=slug, plan=TenantPlan.ENTERPRISE,
               max_users=99, max_mailboxes=99, max_contacts=99999,
               max_campaigns=99, max_leads=99999)
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


def _lead(db, tenant_id, name, website=None, **over):
    over.setdefault("lead_status", LeadStatus.NEW)
    lead = LeadDetails(
        tenant_id=tenant_id, client_name=name, job_title="HR Manager",
        industry="Manufacturing", company_size="120", employer_website=website,
        **over,
    )
    db.add(lead)
    db.commit()
    db.refresh(lead)
    return lead


def _contact(db, tenant_id, client_name, email, lead_id=None):
    c = ContactDetails(tenant_id=tenant_id, client_name=client_name, first_name="Pat",
                       last_name="Lee", email=email, lead_id=lead_id)
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def _billed(db, tenant_id, action):
    """Credits charged to a tenant for one action."""
    return float(db.query(func.coalesce(func.sum(CreditUsage.credits_used), 0)).filter(
        CreditUsage.tenant_id == tenant_id, CreditUsage.usage_type == action,
    ).scalar() or 0)


def _cost(db, action, qty):
    return float(cost_for(action, qty, db=db))


def _use_test_session(monkeypatch, module, db_session):
    """The pipelines open their own SessionLocal — point it at the test session."""
    monkeypatch.setattr(db_session, "close", lambda: None)
    monkeypatch.setattr(module, "SessionLocal", lambda: db_session)


def _contact_dicts(domain, n, prefix="c"):
    return [{"email": f"{prefix}{i}@{domain}", "first_name": f"F{i}", "last_name": f"L{i}",
             "title": "HR Director", "source": "mockpaid"} for i in range(n)]


def _domain_adapter(per_company):
    """Mock contact adapter: company name -> list of contact dicts."""
    adapter = MagicMock()
    adapter.search_contacts = MagicMock(
        side_effect=lambda **kw: [dict(c) for c in per_company.get(kw["company_name"], [])]
    )
    return adapter


def _patch_enrichment(monkeypatch, db_session, adapter):
    monkeypatch.setattr(contact_enrichment, "get_contact_discovery_adapters",
                        lambda db=None, tenant_id=None: [("mockpaid", adapter)])
    monkeypatch.setattr(contact_enrichment.settings, "MAX_CONTACTS_PER_COMPANY_PER_JOB", 4)
    _use_test_session(monkeypatch, contact_enrichment, db_session)


# ---------------------------------------------------------------------------
# A1 — tenant isolation of contact reuse
# ---------------------------------------------------------------------------

def test_a1_reuse_existing_contacts_never_links_another_tenants_contacts(db_session):
    ta, tb = _tenant(db_session, "tenant-a"), _tenant(db_session, "tenant-b")
    lead_a = _lead(db_session, ta.tenant_id, "Acme", "https://acme.com")
    foreign = _contact(db_session, tb.tenant_id, "Acme", "boss@acme.com")

    reused = contact_enrichment._reuse_existing_contacts(db_session, lead_a, 4, lead_domain="acme.com")
    db_session.commit()

    assert reused == 0
    assert db_session.query(LeadContactAssociation).filter(
        LeadContactAssociation.contact_id == foreign.contact_id).count() == 0

    # Positive control: the tenant's OWN cached contact is still reused.
    own = _contact(db_session, ta.tenant_id, "Acme", "own@acme.com")
    assert contact_enrichment._reuse_existing_contacts(db_session, lead_a, 4, lead_domain="acme.com") == 1
    linked = {r.contact_id for r in db_session.query(LeadContactAssociation).filter(
        LeadContactAssociation.lead_id == lead_a.lead_id)}
    assert linked == {own.contact_id}


def test_a1_sibling_auto_enrich_never_touches_another_tenants_leads(db_session):
    ta, tb = _tenant(db_session, "tenant-a"), _tenant(db_session, "tenant-b")
    _contact(db_session, ta.tenant_id, "Acme", "own@acme.com")
    sibling_b = _lead(db_session, tb.tenant_id, "Acme", "https://acme.com")
    counters = {"auto_enriched_leads": 0, "contacts_found": 0, "contacts_reused": 0, "leads_enriched": 0}

    contact_enrichment._auto_enrich_company_siblings(
        db_session, "Acme", set(), 4, [], counters, lead_domain="acme.com", tenant_id=ta.tenant_id,
    )
    db_session.commit()

    db_session.refresh(sibling_b)
    assert sibling_b.first_name is None  # tenant B's lead was not enriched with A's contact
    assert counters["auto_enriched_leads"] == 0
    assert db_session.query(LeadContactAssociation).filter(
        LeadContactAssociation.lead_id == sibling_b.lead_id).count() == 0


def test_a1_auto_enrich_new_leads_ignores_another_tenants_contacts(db_session):
    ta, tb = _tenant(db_session, "tenant-a"), _tenant(db_session, "tenant-b")
    _contact(db_session, tb.tenant_id, "Acme", "boss@acme.com")
    new_lead = _lead(db_session, ta.tenant_id, "Acme", None)

    assert lead_sourcing._auto_enrich_new_leads(db_session, [new_lead], tenant_id=ta.tenant_id) == 0
    db_session.refresh(new_lead)
    assert new_lead.first_name is None


# ---------------------------------------------------------------------------
# A2 — enrichment bills only newly discovered contacts
# ---------------------------------------------------------------------------

def test_a2_enrichment_bills_only_new_contacts_not_cache_reuse(db_session, monkeypatch):
    ta = _tenant(db_session, "tenant-a")
    _contact(db_session, ta.tenant_id, "Acme", "cached@acme.com")  # this tenant's cache
    _lead(db_session, ta.tenant_id, "Acme", "https://acme.com")
    _patch_enrichment(monkeypatch, db_session, _domain_adapter({"Acme": _contact_dicts("acme.com", 2)}))

    result = contact_enrichment.run_contact_enrichment_pipeline(triggered_by="test", tenant_id=ta.tenant_id)

    assert result["contacts_reused"] == 1
    assert result["contacts_new"] == 2
    assert result["contacts_found"] == 3  # what the lead now has (reporting unchanged)
    assert _billed(db_session, ta.tenant_id, "contact_enriched") == _cost(db_session, "contact_enriched", 2)


def test_a2_sibling_cache_links_are_not_billed(db_session, monkeypatch):
    """A sibling lead filled from the cache costs nothing."""
    ta = _tenant(db_session, "tenant-a")
    first = _lead(db_session, ta.tenant_id, "Acme", "https://acme.com")
    sibling = _lead(db_session, ta.tenant_id, "Acme", "https://acme.com", lead_status=LeadStatus.OPEN)
    _patch_enrichment(monkeypatch, db_session, _domain_adapter({"Acme": _contact_dicts("acme.com", 2)}))

    result = contact_enrichment.run_contact_enrichment_pipeline(
        triggered_by="test", tenant_id=ta.tenant_id, lead_ids=[first.lead_id])

    assert result["auto_enriched_leads"] == 1  # the sibling got linked from cache
    assert result["contacts_new"] == 2
    assert _billed(db_session, ta.tenant_id, "contact_enriched") == _cost(db_session, "contact_enriched", 2)
    assert sibling.lead_id  # sanity


# ---------------------------------------------------------------------------
# A3 — a failing row undoes only itself
# ---------------------------------------------------------------------------

def test_a3_enrichment_row_error_keeps_earlier_rows_and_bills_what_is_stored(db_session, monkeypatch):
    ta = _tenant(db_session, "tenant-a")
    _lead(db_session, ta.tenant_id, "Alpha Bakery", "https://alpha.com")
    _lead(db_session, ta.tenant_id, "Beta Bakery", "https://beta.com")
    bad = _contact_dicts("beta.com", 1)
    bad[0]["_organization"] = {"employee_count": 10}  # triggers the failing org update
    _patch_enrichment(monkeypatch, db_session, _domain_adapter({
        "Alpha Bakery": _contact_dicts("alpha.com", 2), "Beta Bakery": bad,
    }))

    def _boom(*a, **k):
        raise RuntimeError("org update failed")
    monkeypatch.setattr(contact_enrichment, "_update_client_from_org_data", _boom)

    result = contact_enrichment.run_contact_enrichment_pipeline(triggered_by="test", tenant_id=ta.tenant_id)

    db_session.expire_all()
    stored = db_session.query(ContactDetails).filter(ContactDetails.tenant_id == ta.tenant_id).count()
    assert stored == 2                     # Alpha's contacts survived Beta's failure
    assert result["contacts_new"] == 2     # Beta's flushed contact is not counted...
    assert result["errors"] == 1
    assert _billed(db_session, ta.tenant_id, "contact_enriched") == _cost(db_session, "contact_enriched", 2)
    assert db_session.query(ContactDetails).filter(ContactDetails.email == "c0@beta.com").count() == 0


def _source_jobs(n, bad_index=None):
    jobs = []
    for i in range(n):
        jobs.append({
            "client_name": f"Company {i}", "job_title": None if i == bad_index else "HR Manager",
            "state": "TX", "job_link": f"https://jobs.example.com/{i}", "source": "mock",
        })
    return jobs


def _patch_sourcing(monkeypatch, db_session, jobs):
    _use_test_session(monkeypatch, lead_sourcing, db_session)
    monkeypatch.setattr(lead_sourcing, "get_all_job_source_adapters", lambda db, tenant_id=None: [])
    monkeypatch.setattr(lead_sourcing, "get_lob_lead_source_adapters", lambda db, tenant_id=None, lob_id=None: [])
    monkeypatch.setattr(lead_sourcing, "deduplicate_jobs", lambda all_jobs, db, tenant_id=None: [dict(j) for j in jobs])
    monkeypatch.setattr(lead_sourcing, "_apply_freshness_gate", lambda jobs_, counters, **kw: jobs_)
    monkeypatch.setattr(lead_sourcing, "_apply_company_gate", lambda db, jobs_, counters, **kw: jobs_)
    monkeypatch.setattr(lead_sourcing, "export_leads_to_xlsx", lambda db, filepath=None: None)


def test_a3_sourcing_row_error_keeps_earlier_rows(db_session, monkeypatch):
    ta = _tenant(db_session, "tenant-a")
    _patch_sourcing(monkeypatch, db_session, _source_jobs(3, bad_index=1))  # NOT NULL violation on row 1

    result = lead_sourcing.run_lead_sourcing_pipeline(["mock"], triggered_by="test", tenant_id=ta.tenant_id)

    db_session.expire_all()
    stored = db_session.query(LeadDetails).filter(LeadDetails.tenant_id == ta.tenant_id).count()
    assert stored == 2
    assert result["inserted"] == 2
    assert result["errors"] == 1
    assert _billed(db_session, ta.tenant_id, "lead_sourced") == _cost(db_session, "lead_sourced", 2)


def test_a3_intent_signal_bad_lead_keeps_earlier_leads(db_session, monkeypatch):
    ta = _tenant(db_session, "tenant-a")
    lob = _lob(db_session, ta.tenant_id)
    _patch_intent(monkeypatch, db_session, [
        {"client_name": "Clinic One"},
        {"client_name": "Clinic Two", "job_title": None},  # NOT NULL violation
        {"client_name": "Clinic Three"},
    ])

    res = intent_signal_monitor.check_intent_signals(tenant_id=ta.tenant_id, lob_id=lob.lob_id)

    db_session.expire_all()
    stored = db_session.query(LeadDetails).filter(LeadDetails.tenant_id == ta.tenant_id).count()
    assert stored == 2 == res["leads_created"]
    assert _billed(db_session, ta.tenant_id, "lead_sourced") == _cost(db_session, "lead_sourced", 2)


# ---------------------------------------------------------------------------
# A4 — incremental metering survives crashes; never double-charges
# ---------------------------------------------------------------------------

def _raise_on_call(n):
    state = {"calls": 0}

    def _check(run_id, db):
        state["calls"] += 1
        if state["calls"] == n:
            raise RuntimeError("worker died")
        return False
    return _check


def test_a4_sourcing_bills_committed_leads_when_post_insert_step_crashes(db_session, monkeypatch):
    ta = _tenant(db_session, "tenant-a")
    _patch_sourcing(monkeypatch, db_session, _source_jobs(12))

    def _export_fails(db, filepath=None):
        raise RuntimeError("disk full")
    monkeypatch.setattr(lead_sourcing, "export_leads_to_xlsx", _export_fails)

    with pytest.raises(RuntimeError):
        lead_sourcing.run_lead_sourcing_pipeline(["mock"], triggered_by="test", tenant_id=ta.tenant_id)

    db_session.expire_all()
    stored = db_session.query(LeadDetails).filter(LeadDetails.tenant_id == ta.tenant_id).count()
    assert stored == 12
    assert _billed(db_session, ta.tenant_id, "lead_sourced") == _cost(db_session, "lead_sourced", 12)


def test_a4_sourcing_mid_loop_crash_bills_exactly_the_checkpointed_leads(db_session, monkeypatch):
    ta = _tenant(db_session, "tenant-a")
    _patch_sourcing(monkeypatch, db_session, _source_jobs(15))
    # Checkpoint at idx 10 commits leads 0-9; the crash at idx 11 loses lead 10.
    monkeypatch.setattr(lead_sourcing, "check_cancel", _raise_on_call(12))

    with pytest.raises(RuntimeError):
        lead_sourcing.run_lead_sourcing_pipeline(["mock"], triggered_by="test", tenant_id=ta.tenant_id)

    db_session.expire_all()
    stored = db_session.query(LeadDetails).filter(LeadDetails.tenant_id == ta.tenant_id).count()
    # 10 on MySQL. pysqlite does not BEGIN before a SAVEPOINT, so on the SQLite test
    # engine releasing lead 10's savepoint already committed it — either way the
    # failure path reconciles against what is STORED.
    assert stored in (10, 11)
    assert _billed(db_session, ta.tenant_id, "lead_sourced") == _cost(db_session, "lead_sourced", stored)


def test_a4_enrichment_crash_bills_stored_contacts_exactly_once(db_session, monkeypatch):
    ta = _tenant(db_session, "tenant-a")
    names = [f"Bakery {chr(65 + i)}" for i in range(7)]
    for i, name in enumerate(names):
        _lead(db_session, ta.tenant_id, name, f"https://bakery{i}.com")
    _patch_enrichment(monkeypatch, db_session, _domain_adapter(
        {name: _contact_dicts(f"bakery{i}.com", 1) for i, name in enumerate(names)}))
    monkeypatch.setattr(contact_enrichment, "check_cancel", _raise_on_call(7))  # dies at idx 6

    with pytest.raises(RuntimeError):
        contact_enrichment.run_contact_enrichment_pipeline(triggered_by="test", tenant_id=ta.tenant_id)

    db_session.expire_all()
    stored = db_session.query(ContactDetails).filter(ContactDetails.tenant_id == ta.tenant_id).count()
    assert stored == 6
    assert _billed(db_session, ta.tenant_id, "contact_enriched") == _cost(db_session, "contact_enriched", 6)


class _ValidAdapter:
    def __init__(self):
        self.calls = 0

    def validate_email(self, email):
        self.calls += 1
        return {"status": ValidationStatus.VALID, "sub_status": None, "raw_response": {}}


def test_a4_validation_crash_bills_stored_results_exactly_once(db_session, monkeypatch):
    ta = _tenant(db_session, "tenant-a")
    _use_test_session(monkeypatch, email_validation, db_session)
    adapter = _ValidAdapter()
    monkeypatch.setattr(email_validation, "get_email_validation_adapter", lambda provider=None: adapter)
    monkeypatch.setattr(email_validation, "check_cancel", _raise_on_call(12))  # dies at idx 11
    emails = [f"person{i}@example.com" for i in range(15)]

    with pytest.raises(RuntimeError):
        email_validation.run_email_validation_pipeline(emails=emails, triggered_by="test", tenant_id=ta.tenant_id)

    db_session.expire_all()
    stored = db_session.query(EmailValidationResult).count()
    assert stored == 11
    assert _billed(db_session, ta.tenant_id, "email_validated") == _cost(db_session, "email_validated", 11)


def test_a4_validation_success_bills_once_and_not_for_cache_hits(db_session, monkeypatch):
    ta = _tenant(db_session, "tenant-a")
    _use_test_session(monkeypatch, email_validation, db_session)
    adapter = _ValidAdapter()
    monkeypatch.setattr(email_validation, "get_email_validation_adapter", lambda provider=None: adapter)
    db_session.add(EmailValidationResult(email="cached@example.com", provider="mock",
                                         status=ValidationStatus.VALID))
    db_session.commit()
    emails = [f"p{i}@example.com" for i in range(23)] + ["cached@example.com"]

    email_validation.run_email_validation_pipeline(emails=emails, triggered_by="test", tenant_id=ta.tenant_id)

    assert adapter.calls == 23
    assert _billed(db_session, ta.tenant_id, "email_validated") == _cost(db_session, "email_validated", 23)


# ---------------------------------------------------------------------------
# A5 — intent signals bill the leads they create
# ---------------------------------------------------------------------------

def _lob(db, tenant_id):
    lob = LineOfBusiness(tenant_id=tenant_id, name="RCM", slug="rcm", lob_type=LOBType.RCM)
    db.add(lob)
    db.commit()
    db.refresh(lob)
    return lob


def _patch_intent(monkeypatch, db_session, leads):
    _use_test_session(monkeypatch, intent_signal_monitor, db_session)
    monkeypatch.setattr(intent_signal_monitor, "get_lob_config", lambda db, lob_id, key: None)
    monkeypatch.setattr(intent_signal_monitor, "_default_signals_for_lob_type",
                        lambda lob_type: {"hiring_signal": {}})
    monkeypatch.setattr(intent_signal_monitor, "_fetch_signal", lambda **kw: [dict(l) for l in leads])


def test_a5_intent_signal_leads_are_billed_to_the_lob_tenant(db_session, monkeypatch):
    ta, tb = _tenant(db_session, "tenant-a"), _tenant(db_session, "tenant-b")
    lob = _lob(db_session, tb.tenant_id)
    _patch_intent(monkeypatch, db_session, [{"client_name": f"Clinic {i}"} for i in range(3)])

    res = intent_signal_monitor.check_intent_signals()  # scheduler: all tenants

    assert res["leads_created"] == 3
    assert _billed(db_session, tb.tenant_id, "lead_sourced") == _cost(db_session, "lead_sourced", 3)
    assert _billed(db_session, ta.tenant_id, "lead_sourced") == 0
    assert _billed(db_session, tb.tenant_id, "intent_scan") == _cost(db_session, "intent_scan", 1)
    assert lob.lob_id


# ---------------------------------------------------------------------------
# A6 — company research metering + caching
# ---------------------------------------------------------------------------

class _FakeAI:
    def __init__(self, payload):
        self.payload = payload
        self.calls = 0

    def research_company(self, company_name, domain=None, location=None):
        self.calls += 1
        return dict(self.payload)


def test_a6_batch_research_is_billed_and_dropped_company_is_not_rebought(db_session, monkeypatch):
    ta = _tenant(db_session, "tenant-a")
    # Incomplete answer (no size) — previously re-researched on every run, forever.
    ai = _FakeAI({"industry": "Information Technology"})
    monkeypatch.setattr(company_enrichment, "_get_ai_adapter", lambda *a, **k: ai)

    for _ in range(2):  # two scheduled runs; the gate drops this company both times
        company_enrichment.resolve_company_metadata_batch(
            db_session, [("Dropped Co", "dropped.com")], tenant_id=ta.tenant_id, max_llm_calls=10)
        db_session.commit()

    assert ai.calls == 1
    assert _billed(db_session, ta.tenant_id, "firmographic_lookup") == _cost(db_session, "firmographic_lookup", 1)
    cached = db_session.query(ClientInfo).filter(
        ClientInfo.tenant_id == ta.tenant_id, ClientInfo.client_name == "Dropped Co").one()
    assert cached.industry == "Information Technology"
    assert cached.status == ClientStatus.INACTIVE and cached.service_count == 0


def test_a6_cached_research_is_served_to_the_gate(db_session, monkeypatch):
    ta = _tenant(db_session, "tenant-a")
    ai = _FakeAI({"industry": "Retail", "employee_count": 9000})
    monkeypatch.setattr(company_enrichment, "_get_ai_adapter", lambda *a, **k: ai)

    first = company_enrichment.resolve_company_metadata_batch(
        db_session, [("Big Box", "")], tenant_id=ta.tenant_id, max_llm_calls=10)
    db_session.commit()
    second = company_enrichment.resolve_company_metadata_batch(
        db_session, [("Big Box", "")], tenant_id=ta.tenant_id, max_llm_calls=10)

    assert ai.calls == 1
    assert second["big box"]["employee_count"] == first["big box"]["employee_count"] == 9000


def test_a6_free_only_gate_research_is_not_billed(db_session, monkeypatch):
    ta = _tenant(db_session, "tenant-a")
    ai = _FakeAI({"industry": "Retail"})
    monkeypatch.setattr(company_enrichment, "_get_ai_adapter", lambda *a, **k: ai)

    company_enrichment.resolve_company_metadata_batch(
        db_session, [("Shop", "")], tenant_id=ta.tenant_id, max_llm_calls=10, free_only=True)

    assert ai.calls == 1
    assert _billed(db_session, ta.tenant_id, "firmographic_lookup") == 0


def test_a6_enrich_from_llm_bills_and_stops_on_permanently_null_fields(db_session, monkeypatch):
    ta = _tenant(db_session, "tenant-a")
    client = ClientInfo(tenant_id=ta.tenant_id, client_name="Acme", website="https://acme.com",
                        industry="Retail", company_size="51-200", employee_count=120)
    db_session.add(client)
    db_session.commit()
    # The model never knows description / founded_year / HQ / LinkedIn for Acme.
    ai = _FakeAI({})
    monkeypatch.setattr(company_enrichment, "_get_ai_adapter", lambda *a, **k: ai)

    for _ in range(3):
        company_enrichment.enrich_from_llm(db_session, client, tenant_id=ta.tenant_id)
        db_session.commit()

    assert ai.calls == 1
    assert _billed(db_session, ta.tenant_id, "firmographic_lookup") == _cost(db_session, "firmographic_lookup", 1)


def test_a6_bulk_enrich_ignores_another_tenants_client(db_session, monkeypatch):
    ta, tb = _tenant(db_session, "tenant-a"), _tenant(db_session, "tenant-b")
    foreign = ClientInfo(tenant_id=tb.tenant_id, client_name="Foreign Co")
    db_session.add(foreign)
    db_session.commit()
    monkeypatch.setattr(company_enrichment, "_get_ai_adapter", lambda *a, **k: None)

    out = company_enrichment.bulk_enrich_clients(db_session, [foreign.client_id], tenant_id=ta.tenant_id)

    assert out["results"] == [{"client_id": foreign.client_id, "error": "Not found"}]
    db_session.refresh(foreign)
    assert (foreign.enrich_attempts or 0) == 0
