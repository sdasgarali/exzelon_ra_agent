"""Credit-metering loopholes (Plan_Credit_Loopholes.md, Agent C items C1-C8).

Every test here pins a hole that let work happen without the tenant paying for it,
or let a tenant spend past what it had. Each item's core test fails on decc862; the
few that pass there (template fallback free, unused allowance not rolled over, keyword
classification free, first summary free, ...) guard the "don't over-charge" side.
"""
from datetime import date
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Query

from app.core.credit_costs import CREDIT_COSTS, cost_for, estimate_run_credits
from app.db.models.credit_balance import TenantCreditBalance
from app.db.models.credit_usage import CreditUsage
from app.services.credit_metering import (
    check_credit_budget, get_balance, has_credit_budget, refill_all_balances,
    refill_if_new_period, spend,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _enforce(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "CREDIT_ENFORCEMENT_ENABLED", True)


def _set_available(db, tenant_id, credits):
    balance = get_balance(db, tenant_id)
    balance.allowance_credits = float(credits)
    balance.topup_credits = 0.0
    db.commit()
    return balance


def _usage(db, tenant_id, action=None):
    db.expire_all()
    q = db.query(CreditUsage).filter(CreditUsage.tenant_id == tenant_id)
    if action:
        q = q.filter(CreditUsage.usage_type == action)
    return q.all()


class _LockSpy:
    """Counts Query.with_for_update() calls (a no-op on SQLite, so the only way to
    see that a lock was *requested*)."""

    def __init__(self, monkeypatch):
        self.calls = 0
        original = Query.with_for_update
        spy = self

        def _wrapped(self_q, *a, **k):
            spy.calls += 1
            return original(self_q, *a, **k)

        monkeypatch.setattr(Query, "with_for_update", _wrapped)


# ---------------------------------------------------------------------------
# C3 — overspend carried forward, not wiped at the month turn
# ---------------------------------------------------------------------------

def test_c3_refill_carries_negative_balance_forward(db_session, test_tenant):
    balance = get_balance(db_session, test_tenant.tenant_id)
    balance.allowance_credits = -500.0          # overspent last month
    balance.topup_credits = 40.0
    balance.period_start = date(2020, 1, 1)
    db_session.commit()

    assert refill_if_new_period(db_session, balance) is True
    assert balance.allowance_credits == 25_000 - 500   # debt comes out of the new month
    assert balance.topup_credits == 40.0                # top-ups untouched


def test_c3_refill_does_not_roll_over_unused_allowance(db_session, test_tenant):
    balance = get_balance(db_session, test_tenant.tenant_id)
    balance.allowance_credits = 1_234.0
    balance.period_start = date(2020, 1, 1)
    db_session.commit()

    refill_if_new_period(db_session, balance)
    assert balance.allowance_credits == 25_000


def test_c3_debt_larger_than_plan_keeps_tenant_blocked(db_session, starter_tenant, monkeypatch):
    _enforce(monkeypatch)
    balance = get_balance(db_session, starter_tenant.tenant_id)
    balance.allowance_credits = -1_000.0   # Free plan is 300/mo
    balance.period_start = date(2020, 1, 1)
    db_session.commit()

    with pytest.raises(HTTPException) as exc:
        check_credit_budget(db_session, starter_tenant.tenant_id, credits_needed=1)
    assert exc.value.status_code == 402
    assert get_balance(db_session, starter_tenant.tenant_id).allowance_credits == 300 - 1_000


# ---------------------------------------------------------------------------
# C5 — refills take the row lock
# ---------------------------------------------------------------------------

def test_c5_gate_locks_the_row_before_a_lazy_refill(db_session, test_tenant, monkeypatch):
    _enforce(monkeypatch)
    balance = get_balance(db_session, test_tenant.tenant_id)
    balance.period_start = date(2020, 1, 1)
    db_session.commit()

    spy = _LockSpy(monkeypatch)
    check_credit_budget(db_session, test_tenant.tenant_id, credits_needed=1)
    assert spy.calls >= 1
    assert get_balance(db_session, test_tenant.tenant_id).period_start == date.today().replace(day=1)


def test_c5_unlocked_read_of_a_current_balance_takes_no_lock(db_session, test_tenant, monkeypatch):
    get_balance(db_session, test_tenant.tenant_id)  # create, current period
    db_session.commit()
    spy = _LockSpy(monkeypatch)
    get_balance(db_session, test_tenant.tenant_id)
    assert spy.calls == 0  # reads stay cheap; only refills lock


def test_c5_refill_all_balances_locks_each_row(db_session, test_tenant, professional_capped_tenant, monkeypatch):
    for t in (test_tenant, professional_capped_tenant):
        get_balance(db_session, t.tenant_id).period_start = date(2020, 1, 1)
    db_session.commit()

    spy = _LockSpy(monkeypatch)
    assert refill_all_balances(db_session) == 2
    assert spy.calls >= 2


# ---------------------------------------------------------------------------
# C2 — the gate asks for an estimate, not 1 credit
# ---------------------------------------------------------------------------

def test_c2_run_estimates_are_conservative_and_capped():
    assert estimate_run_credits("lead_sourcing") == 50 * cost_for("lead_sourced")
    assert estimate_run_credits("contact_enrichment", units=5, per_unit_multiplier=4) == 5 * 4 * 3
    assert estimate_run_credits("contact_enrichment", per_unit_multiplier=4) == 10 * 4 * 3
    assert estimate_run_credits("email_validation", units=7) == 7
    assert estimate_run_credits("email_validation") == 25
    assert estimate_run_credits("contact_enrichment", units=10_000, per_unit_multiplier=4) == 1_000


def _pipeline_headers(db_session, test_tenant, sa_headers, monkeypatch, credits):
    """Enforcement on, `credits` available, pipelines stubbed. Returns headers for a
    super admin impersonating `test_tenant` (the run endpoints check module-tab
    permissions the plain admin fixture doesn't carry)."""
    _enforce(monkeypatch)
    _set_available(db_session, test_tenant.tenant_id, credits)
    # The background task must never actually run a pipeline in a unit test.
    import app.services.pipelines.lead_sourcing as ls
    import app.services.pipelines.contact_enrichment as ce
    import app.services.pipelines.email_validation as ev
    monkeypatch.setattr(ls, "run_lead_sourcing_pipeline", lambda **k: {})
    monkeypatch.setattr(ce, "run_contact_enrichment_pipeline", lambda **k: {})
    monkeypatch.setattr(ev, "run_email_validation_pipeline", lambda **k: {})
    return {**sa_headers, "X-Tenant-ID": str(test_tenant.tenant_id)}


def test_c2_one_credit_cannot_launch_lead_sourcing(client, db_session, test_tenant, sa_headers, monkeypatch):
    h = _pipeline_headers(db_session, test_tenant, sa_headers, monkeypatch, credits=1)
    r = client.post("/api/v1/pipelines/lead-sourcing/run", headers=h)
    assert r.status_code == 402


def test_c2_enough_credits_launches_lead_sourcing(client, db_session, test_tenant, sa_headers, monkeypatch):
    h = _pipeline_headers(db_session, test_tenant, sa_headers, monkeypatch, credits=500)
    r = client.post("/api/v1/pipelines/lead-sourcing/run", headers=h)
    assert r.status_code == 200, r.text


def test_c2_enrichment_gate_scales_with_selected_leads(client, db_session, test_tenant, sa_headers, monkeypatch):
    # 20 leads x 4 contacts x 3 credits = 240 needed; 100 available.
    h = _pipeline_headers(db_session, test_tenant, sa_headers, monkeypatch, credits=100)
    r = client.post("/api/v1/pipelines/contact-enrichment/run", headers=h,
                    json={"lead_ids": list(range(1, 21))})
    assert r.status_code == 402
    # 2 leads x 4 x 3 = 24 → fits.
    r = client.post("/api/v1/pipelines/contact-enrichment/run", headers=h,
                    json={"lead_ids": [1, 2]})
    assert r.status_code == 200, r.text


def test_c2_validation_gate_needs_more_than_one_credit(client, db_session, test_tenant, sa_headers, monkeypatch):
    h = _pipeline_headers(db_session, test_tenant, sa_headers, monkeypatch, credits=3)
    r = client.post("/api/v1/pipelines/email-validation/run", headers=h)
    assert r.status_code == 402


def test_c2_spend_still_never_raises_past_zero(db_session, test_tenant):
    _set_available(db_session, test_tenant.tenant_id, 1)
    spend(db_session, test_tenant.tenant_id, "contact_enriched", 10, commit=True)
    assert get_balance(db_session, test_tenant.tenant_id).allowance_credits == 1 - 30


# ---------------------------------------------------------------------------
# C4 — has_credit_budget (scheduler helper)
# ---------------------------------------------------------------------------

def test_c4_has_credit_budget(db_session, test_tenant, monkeypatch):
    tid = test_tenant.tenant_id
    _set_available(db_session, tid, 10)
    # Enforcement off → always True.
    assert has_credit_budget(db_session, tid, 1_000) is True
    _enforce(monkeypatch)
    assert has_credit_budget(db_session, tid, 5) is True
    assert has_credit_budget(db_session, tid, 50) is False
    assert has_credit_budget(db_session, None, 10**9) is True  # internal work


# ---------------------------------------------------------------------------
# C4 — scheduled pipelines check the tenant's budget first
# ---------------------------------------------------------------------------

def _scheduler_for(monkeypatch, tenant_id):
    from app.services.warmup import scheduler
    from tests.conftest import TestingSessionLocal
    monkeypatch.setattr(scheduler, "_get_db", lambda: TestingSessionLocal())
    monkeypatch.setattr(scheduler, "_get_active_tenant_ids", lambda: [tenant_id])
    return scheduler


def _record(calls, name, result=None):
    def _fn(*a, **k):
        calls.append(name)
        return result if result is not None else {}
    return _fn


def test_c4_scheduled_sourcing_skipped_when_out_of_credits(db_session, test_tenant, monkeypatch):
    _enforce(monkeypatch)
    _set_available(db_session, test_tenant.tenant_id, 1)
    scheduler = _scheduler_for(monkeypatch, test_tenant.tenant_id)
    calls = []
    monkeypatch.setattr("app.services.pipelines.lead_sourcing.run_lead_sourcing_pipeline",
                        _record(calls, "sourcing", {"inserted": 0}))
    scheduler._job_lead_sourcing_run_inner()
    assert calls == []


def test_c4_scheduled_sourcing_runs_with_credits(db_session, test_tenant, monkeypatch):
    _enforce(monkeypatch)
    _set_available(db_session, test_tenant.tenant_id, 1_000)
    scheduler = _scheduler_for(monkeypatch, test_tenant.tenant_id)
    calls = []
    monkeypatch.setattr("app.services.pipelines.lead_sourcing.run_lead_sourcing_pipeline",
                        _record(calls, "sourcing", {"inserted": 0}))
    scheduler._job_lead_sourcing_run_inner()
    assert calls == ["sourcing"]


def test_c4_scheduled_sourcing_ignores_budget_when_enforcement_off(db_session, test_tenant, monkeypatch):
    _set_available(db_session, test_tenant.tenant_id, -50)
    scheduler = _scheduler_for(monkeypatch, test_tenant.tenant_id)
    calls = []
    monkeypatch.setattr("app.services.pipelines.lead_sourcing.run_lead_sourcing_pipeline",
                        _record(calls, "sourcing", {"inserted": 0}))
    scheduler._job_lead_sourcing_run_inner()
    assert calls == ["sourcing"]


def test_c4_auto_chain_skips_enrichment_and_validation_without_credits(db_session, test_tenant, monkeypatch):
    _enforce(monkeypatch)
    _set_available(db_session, test_tenant.tenant_id, 2)
    from app.services.warmup import scheduler
    monkeypatch.setattr("app.core.settings_resolver.get_tenant_setting_bool",
                        lambda *a, **k: True)
    calls = []
    monkeypatch.setattr("app.services.pipelines.contact_enrichment.run_contact_enrichment_pipeline",
                        _record(calls, "enrichment"))
    monkeypatch.setattr("app.services.pipelines.email_validation.run_email_validation_pipeline",
                        _record(calls, "validation"))
    monkeypatch.setattr("app.services.auto_enrollment.run_auto_enrollment",
                        _record(calls, "enrollment", {"total_enrolled": 0}))
    scheduler._run_auto_chain(db_session, leads_inserted=5, tenant_id=test_tenant.tenant_id)
    assert "enrichment" not in calls and "validation" not in calls
    assert "enrollment" in calls  # free step still runs


# ---------------------------------------------------------------------------
# C1 / C8 — AI endpoint charges persist; only real AI output is charged
# ---------------------------------------------------------------------------

def _track_commit_after_charge(monkeypatch, db):
    """Record the order of credit spends and session commits during a request.

    `db_session.rollback()` can't prove an endpoint committed: pysqlite's SAVEPOINT
    handling (which `spend()` uses via begin_nested) effectively auto-commits on
    SQLite, while on MySQL the uncommitted charge is discarded when `get_db` closes.
    So assert the real contract: a commit happens *after* the charge.
    """
    import app.services.credit_metering as cm
    events = []
    real_spend = cm.spend

    def _spend(*a, **k):
        out = real_spend(*a, **k)
        if out is not None:
            events.append("charge")
        return out

    real_commit = db.commit

    def _commit():
        events.append("commit")
        return real_commit()

    monkeypatch.setattr(cm, "spend", _spend)
    monkeypatch.setattr(db, "commit", _commit)
    return events


def _committed_after_charge(events):
    return "charge" in events and "commit" in events[events.index("charge"):]


def _fake_adapter(monkeypatch, text):
    adapter = MagicMock()
    adapter._call_api.return_value = text
    monkeypatch.setattr("app.services.adapters.ai_content.get_ai_adapter",
                        lambda db, tenant_id=None: adapter)
    return adapter


_SEQ_JSON = ('[{"step_order":1,"subject":"Hi","body_html":"<p>a</p>","delay_days":0},'
             '{"step_order":2,"subject":"Re","body_html":"<p>b</p>","delay_days":3}]')
_ICP_JSON = ('{"industries":["Healthcare"],"job_titles":["HR Manager"],"states":["TX"],'
             '"company_sizes":["51-200"],"rationale":"fit"}')


def test_c1_sequence_generator_charge_is_committed(client, db_session, test_tenant, auth_headers, monkeypatch):
    _fake_adapter(monkeypatch, _SEQ_JSON)
    events = _track_commit_after_charge(monkeypatch, db_session)
    r = client.post("/api/v1/sequence-generator/generate", headers=auth_headers,
                    json={"goal": "book meetings", "product": "staffing", "num_steps": 2})
    assert r.status_code == 200, r.text
    assert _committed_after_charge(events), events
    rows = _usage(db_session, test_tenant.tenant_id, "ai_sequence")
    assert len(rows) == 1 and rows[0].credits_used == cost_for("ai_sequence")


def test_c1_sequence_template_fallback_is_free(client, db_session, test_tenant, auth_headers, monkeypatch):
    monkeypatch.setattr("app.services.adapters.ai_content.get_ai_adapter",
                        lambda db, tenant_id=None: None)
    r = client.post("/api/v1/sequence-generator/generate", headers=auth_headers,
                    json={"goal": "x", "product": "y"})
    assert r.status_code == 200
    assert _usage(db_session, test_tenant.tenant_id, "ai_sequence") == []


def test_c1_sequence_generator_is_gated(client, db_session, test_tenant, auth_headers, monkeypatch):
    _enforce(monkeypatch)
    _set_available(db_session, test_tenant.tenant_id, cost_for("ai_sequence") - 1)
    adapter = _fake_adapter(monkeypatch, _SEQ_JSON)
    r = client.post("/api/v1/sequence-generator/generate", headers=auth_headers,
                    json={"goal": "x", "product": "y"})
    assert r.status_code == 402
    adapter._call_api.assert_not_called()


def test_c8_icp_wizard_ai_path_runs_and_charge_is_committed(client, db_session, test_tenant, auth_headers, monkeypatch):
    adapter = _fake_adapter(monkeypatch, _ICP_JSON)
    events = _track_commit_after_charge(monkeypatch, db_session)
    r = client.post("/api/v1/icp/generate", headers=auth_headers, json={
        "company_description": "staffing", "offering": "nurses", "pain_points": "shortage"})
    assert r.status_code == 200, r.text
    assert _committed_after_charge(events), events
    assert r.json()["ai_generated"] is True
    assert r.json()["industries"] == ["Healthcare"]
    adapter._call_api.assert_called_once()
    rows = _usage(db_session, test_tenant.tenant_id, "icp_wizard")
    assert len(rows) == 1 and rows[0].credits_used == 10


def test_c8_icp_rule_based_fallback_is_free(client, db_session, test_tenant, auth_headers, monkeypatch):
    _fake_adapter(monkeypatch, "not json at all")
    r = client.post("/api/v1/icp/generate", headers=auth_headers, json={
        "company_description": "hospital staffing", "offering": "nurses", "pain_points": "x"})
    assert r.status_code == 200
    assert r.json()["ai_generated"] is False
    assert _usage(db_session, test_tenant.tenant_id, "icp_wizard") == []


def _preview_campaign(db, tenant_id, n_contacts=2):
    from app.db.models.campaign import (
        Campaign, CampaignContact, CampaignContactStatus, CampaignStatus, SequenceStep, StepType,
    )
    from app.db.models.contact import ContactDetails
    camp = Campaign(tenant_id=tenant_id, name="Preview", status=CampaignStatus.DRAFT)
    db.add(camp)
    db.flush()
    db.add(SequenceStep(campaign_id=camp.campaign_id, step_order=0, step_type=StepType.EMAIL,
                        subject="Hi {{contact_first_name}}", body_html="<p>hello</p>"))
    for i in range(n_contacts):
        ct = ContactDetails(tenant_id=tenant_id, client_name="Acme", first_name=f"F{i}",
                            last_name="L", email=f"p{i}@acme.example.com")
        db.add(ct)
        db.flush()
        db.add(CampaignContact(campaign_id=camp.campaign_id, contact_id=ct.contact_id,
                               status=CampaignContactStatus.ACTIVE, current_step=1))
    db.commit()
    return camp


def _fake_personaliser(monkeypatch):
    def _personalise(db, tenant_id, subject, body_html, body_text, contact, lead):
        from app.services.credit_metering import meter
        meter(db, tenant_id, "ai_personalization", reference_id=str(contact.contact_id))
        return {"subject": subject, "body_html": body_html, "body_text": body_text,
                "ai_used": True, "tokens_used": 10}
    monkeypatch.setattr("app.services.ai_personalizer.personalize_email_for_contact", _personalise)


def test_c1_preview_personalization_charges_are_committed(client, db_session, test_tenant, auth_headers, monkeypatch):
    camp = _preview_campaign(db_session, test_tenant.tenant_id, n_contacts=2)
    _fake_personaliser(monkeypatch)
    events = _track_commit_after_charge(monkeypatch, db_session)
    r = client.post("/api/v1/email-preview/preview-personalization", headers=auth_headers,
                    json={"campaign_id": camp.campaign_id, "step_index": 0})
    assert r.status_code == 200, r.text
    assert _committed_after_charge(events), events
    assert len(_usage(db_session, test_tenant.tenant_id, "ai_personalization")) == 2


def test_c1_preview_personalization_is_gated_on_batch_size(client, db_session, test_tenant, auth_headers, monkeypatch):
    camp = _preview_campaign(db_session, test_tenant.tenant_id, n_contacts=3)
    _enforce(monkeypatch)
    _set_available(db_session, test_tenant.tenant_id, 2)  # 3 contacts x 1 credit needed
    _fake_personaliser(monkeypatch)
    r = client.post("/api/v1/email-preview/preview-personalization", headers=auth_headers,
                    json={"campaign_id": camp.campaign_id, "step_index": 0})
    assert r.status_code == 402


# ---------------------------------------------------------------------------
# C7 — Stripe top-ups granted only once the money has actually arrived
# ---------------------------------------------------------------------------

def _stripe_returns(monkeypatch, event):
    from app.core.config import settings
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test", raising=False)
    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", "whsec_test", raising=False)
    import stripe
    monkeypatch.setattr(stripe.Webhook, "construct_event", lambda *a, **k: event, raising=True)


def _topup_event(event_id, tenant_id, etype="checkout.session.completed",
                 payment_status="paid", session_id="cs_topup_1", credits=1000):
    return {
        "id": event_id, "type": etype,
        "data": {"object": {
            "id": session_id, "payment_status": payment_status, "amount_total": 1000,
            "metadata": {"purpose": "credit_topup", "tenant_id": str(tenant_id),
                         "credits": str(credits)},
        }},
    }


def _post_webhook(client):
    return client.post("/api/v1/billing/webhook/stripe", content=b"{}",
                       headers={"stripe-signature": "t=1,v1=x"})


def _lots(db, tenant_id):
    from app.db.models.credit_topup_lot import CreditTopupLot
    db.expire_all()
    return db.query(CreditTopupLot).filter(CreditTopupLot.tenant_id == tenant_id).all()


def test_c7_unpaid_checkout_grants_nothing(client, db_session, test_tenant, monkeypatch):
    _stripe_returns(monkeypatch, _topup_event("evt_u1", test_tenant.tenant_id, payment_status="unpaid"))
    assert _post_webhook(client).status_code == 200
    assert _lots(db_session, test_tenant.tenant_id) == []


def test_c7_async_payment_succeeded_grants_once(client, db_session, test_tenant, monkeypatch):
    tid = test_tenant.tenant_id
    _stripe_returns(monkeypatch, _topup_event("evt_a1", tid, payment_status="unpaid"))
    _post_webhook(client)
    _stripe_returns(monkeypatch, _topup_event(
        "evt_a2", tid, etype="checkout.session.async_payment_succeeded"))
    assert _post_webhook(client).status_code == 200
    lots = _lots(db_session, tid)
    assert len(lots) == 1 and lots[0].credits_purchased == 1000


def test_c7_same_session_cannot_be_granted_by_both_events(client, db_session, test_tenant, monkeypatch):
    tid = test_tenant.tenant_id
    _stripe_returns(monkeypatch, _topup_event("evt_b1", tid, payment_status="paid"))
    _post_webhook(client)
    _stripe_returns(monkeypatch, _topup_event(
        "evt_b2", tid, etype="checkout.session.async_payment_succeeded"))
    _post_webhook(client)
    assert len(_lots(db_session, tid)) == 1
    assert get_balance(db_session, tid).topup_credits == 1000


def test_c7_unpaid_invoice_checkout_is_not_marked_paid(client, db_session, test_tenant, monkeypatch):
    from app.db.models.invoice import Invoice, InvoiceStatus
    inv = Invoice(tenant_id=test_tenant.tenant_id, invoice_number="INV-2026-7001",
                  period_start=date(2026, 1, 1), period_end=date(2026, 1, 31),
                  due_date=date(2026, 2, 5), subtotal_cents=5000, tax_cents=0,
                  total_cents=5000, currency="USD", status=InvoiceStatus.SENT)
    db_session.add(inv)
    db_session.commit()

    def _evt(eid, etype, ps):
        return {"id": eid, "type": etype, "data": {"object": {
            "id": "cs_inv", "payment_intent": "pi_x", "amount_total": 5000, "payment_status": ps,
            "metadata": {"invoice_id": str(inv.invoice_id), "tenant_id": str(test_tenant.tenant_id)},
        }}}

    _stripe_returns(monkeypatch, _evt("evt_i1", "checkout.session.completed", "unpaid"))
    assert _post_webhook(client).status_code == 200
    db_session.expire_all()
    assert db_session.get(Invoice, inv.invoice_id).status == InvoiceStatus.SENT

    _stripe_returns(monkeypatch, _evt("evt_i2", "checkout.session.async_payment_succeeded", "paid"))
    assert _post_webhook(client).status_code == 200
    db_session.expire_all()
    assert db_session.get(Invoice, inv.invoice_id).status == InvoiceStatus.PAID


# ---------------------------------------------------------------------------
# C6 — AI calls that used to run unmetered
# ---------------------------------------------------------------------------

def _contact(db, tenant_id, email="c6@acme.example.com"):
    from app.db.models.contact import ContactDetails
    c = ContactDetails(tenant_id=tenant_id, client_name="Acme", first_name="Ann",
                       last_name="Lee", email=email)
    db.add(c)
    db.commit()
    return c


def test_c6_outreach_draft_charges_per_successful_draft(db_session, test_tenant, monkeypatch):
    import app.services.outreach_draft_service as ods
    contact = _contact(db_session, test_tenant.tenant_id)
    adapter = MagicMock()
    adapter.research_company.return_value = {}
    adapter.generate_email.return_value = {"subject": "Hi", "body_html": "<p>x</p>", "body_text": "x"}
    monkeypatch.setattr(ods, "get_tenant_setting_bool", lambda *a, **k: True)
    monkeypatch.setattr(ods, "get_ai_adapter", lambda db, tenant_id=None: adapter)

    assert ods.draft_outreach_email(db_session, contact, tenant_id=test_tenant.tenant_id) is not None
    assert len(_usage(db_session, test_tenant.tenant_id, "ai_personalization")) == 1

    adapter.generate_email.return_value = {"subject": "Hi", "body_html": "<p>x</p>", "error": "fallback"}
    assert ods.draft_outreach_email(db_session, contact, tenant_id=test_tenant.tenant_id) is None
    assert len(_usage(db_session, test_tenant.tenant_id, "ai_personalization")) == 1  # unchanged


def test_c6_ai_rewrite_is_charged(db_session, test_tenant, sample_mailbox, monkeypatch):
    from app.db.models.outreach_draft import DraftSource, DraftStatus, OutreachDraft
    from app.services.email_preview_service import ai_rewrite_draft
    contact = _contact(db_session, test_tenant.tenant_id)
    draft = OutreachDraft(tenant_id=test_tenant.tenant_id, contact_id=contact.contact_id,
                          mailbox_id=sample_mailbox.mailbox_id, subject="s", body_html="<p>b</p>",
                          status=DraftStatus.PENDING, source=DraftSource.PIPELINE)
    db_session.add(draft)
    db_session.commit()
    _fake_adapter(monkeypatch, "SUBJECT: new\nBODY: <p>new</p>")
    events = _track_commit_after_charge(monkeypatch, db_session)
    result = ai_rewrite_draft(draft.draft_id, db_session, test_tenant.tenant_id)
    assert result.get("ai_rewritten") is True
    assert _committed_after_charge(events), events
    assert len(_usage(db_session, test_tenant.tenant_id, "ai_personalization")) == 1


def test_c6_spam_suggestions_charged_only_when_ai_answers(db_session, test_tenant, monkeypatch):
    from app.services.email_preview_service import check_spam_and_suggest
    adapter = _fake_adapter(monkeypatch, '[{"original": "free", "replacement": "no-cost"}]')
    subject, body = "FREE money guaranteed", "<p>Act now, 100% free, risk free guarantee</p>"

    out = check_spam_and_suggest(subject, body, db_session, test_tenant.tenant_id, allow_ai=False)
    adapter._call_api.assert_not_called()
    assert out["flagged_words"]
    assert _usage(db_session, test_tenant.tenant_id, "ai_personalization") == []

    check_spam_and_suggest(subject, body, db_session, test_tenant.tenant_id)
    assert len(_usage(db_session, test_tenant.tenant_id, "ai_personalization")) == 1


def _campaign_with_lead(db, tenant_id):
    from app.db.models.campaign import Campaign, CampaignStatus
    camp = Campaign(tenant_id=tenant_id, name="Camp", status=CampaignStatus.DRAFT)
    db.add(camp)
    db.commit()
    return camp


def test_c6_subject_suggestions_use_ai_and_charge(client, db_session, test_tenant, auth_headers, monkeypatch):
    camp = _campaign_with_lead(db_session, test_tenant.tenant_id)
    _fake_adapter(monkeypatch, '{"subjects": ["Hi {{first_name}}", "Quick q for {{company}}"]}')
    events = _track_commit_after_charge(monkeypatch, db_session)
    r = client.post(f"/api/v1/campaigns/{camp.campaign_id}/ai-suggest-subjects", headers=auth_headers)
    assert r.status_code == 200, r.text
    assert r.json()["source"] == "ai"
    assert r.json()["subjects"][0] == "Hi {{first_name}}"
    assert _committed_after_charge(events), events
    assert len(_usage(db_session, test_tenant.tenant_id, "ai_suggestion")) == 1


def test_c6_campaign_naming_charges_and_falls_back_free_when_broke(client, db_session, test_tenant, auth_headers, monkeypatch):
    camp = _campaign_with_lead(db_session, test_tenant.tenant_id)
    adapter = _fake_adapter(monkeypatch, '{"name": "Healthcare HR push", "description": "d"}')
    r = client.post(f"/api/v1/campaigns/{camp.campaign_id}/ai-enhance", headers=auth_headers)
    assert r.json()["suggested_name"] == "Healthcare HR push"
    assert len(_usage(db_session, test_tenant.tenant_id, "ai_suggestion")) == 1

    _enforce(monkeypatch)
    _set_available(db_session, test_tenant.tenant_id, 0)
    adapter._call_api.reset_mock()
    r = client.post(f"/api/v1/campaigns/{camp.campaign_id}/ai-enhance", headers=auth_headers)
    assert r.status_code == 200  # rule-based suggestion, no 402
    adapter._call_api.assert_not_called()
    assert len(_usage(db_session, test_tenant.tenant_id, "ai_suggestion")) == 1


def _thread(db, tenant_id, contact):
    from app.db.models.inbox_message import InboxMessage, MessageDirection
    db.add(InboxMessage(tenant_id=tenant_id, thread_id="thr-c6", contact_id=contact.contact_id,
                        direction=MessageDirection.RECEIVED, from_email=contact.email,
                        to_email="me@x.example.com", subject="Re: hello",
                        body_text="What does it cost?"))
    db.commit()


def test_c6_inbox_suggest_reply_is_charged_and_committed(client, db_session, test_tenant, auth_headers, monkeypatch):
    contact = _contact(db_session, test_tenant.tenant_id)
    _thread(db_session, test_tenant.tenant_id, contact)
    _fake_adapter(monkeypatch, "Happy to share pricing — 15 minutes Thursday?")
    events = _track_commit_after_charge(monkeypatch, db_session)
    r = client.post("/api/v1/inbox/threads/thr-c6/suggest-reply", headers=auth_headers)
    assert r.status_code == 200, r.text
    assert _committed_after_charge(events), events
    rows = _usage(db_session, test_tenant.tenant_id, "ai_reply")
    assert len(rows) == 1 and rows[0].credits_used == 2


def test_c6_inbox_suggest_reply_is_gated(client, db_session, test_tenant, auth_headers, monkeypatch):
    contact = _contact(db_session, test_tenant.tenant_id)
    _thread(db_session, test_tenant.tenant_id, contact)
    _enforce(monkeypatch)
    _set_available(db_session, test_tenant.tenant_id, 1)
    adapter = _fake_adapter(monkeypatch, "x")
    r = client.post("/api/v1/inbox/threads/thr-c6/suggest-reply", headers=auth_headers)
    assert r.status_code == 402
    adapter._call_api.assert_not_called()


def test_c6_sentiment_ai_classification_is_metered_to_the_reply_tenant(db_session, test_tenant, monkeypatch):
    from app.services.ai_sentiment import analyze_reply_sentiment
    _fake_adapter(monkeypatch, "question|neutral|0.7")
    out = analyze_reply_sentiment("What would pricing look like for 3 sites?", "Re: x",
                                  db_session, tenant_id=test_tenant.tenant_id)
    assert out["category"] == "question"
    rows = _usage(db_session, test_tenant.tenant_id, "ai_classification")
    assert len(rows) == 1 and rows[0].credits_used == 0.5

    # Keyword rule decides → no AI call, no charge.
    analyze_reply_sentiment("Not interested, thanks", "", db_session, tenant_id=test_tenant.tenant_id)
    assert len(_usage(db_session, test_tenant.tenant_id, "ai_classification")) == 1


@pytest.mark.parametrize("reasoning,charged", [
    ("The sender says they are travelling until Monday", 1),   # LLM classification
    ("Keyword match: ooo (2 hits)", 0),                          # keyword fallback: free
])
def test_c6_reply_agent_ooo_exit_charges_llm_classification(db_session, test_tenant, monkeypatch, reasoning, charged):
    from app.db.models.inbox_message import InboxMessage, MessageDirection
    from app.services.ai_reply_agent_service import generate_ai_reply_draft
    monkeypatch.setattr("app.services.ai_sales_agent.orchestrator.orchestrate_reply",
                        lambda **k: {"intent": "ooo", "confidence": 90,
                                     "classification": {"reasoning": reasoning}})
    msg = InboxMessage(tenant_id=test_tenant.tenant_id, thread_id="thr-ooo",
                       direction=MessageDirection.RECEIVED, from_email="a@b.example.com",
                       to_email="me@x.example.com", body_text="I'm away")
    assert generate_ai_reply_draft(db_session, "thr-ooo", msg, None, None, test_tenant.tenant_id) is None
    assert len(_usage(db_session, test_tenant.tenant_id, "ai_classification")) == charged


def _finished_run(db, tenant_id, summary_json=None):
    from app.db.models.job_run import JobRun, JobStatus
    run = JobRun(tenant_id=tenant_id, pipeline_name="contact_enrichment", status=JobStatus.COMPLETED,
                 counters_json='{"contacts_found": 3}', triggered_by="t@t.example.com",
                 summary_json=summary_json)
    db.add(run)
    db.commit()
    return run


@pytest.mark.parametrize("existing,charged", [
    (None, 0),                                              # first summary: free
    ('{"summary": "old", "source_breakdown": []}', 1),      # user-forced regenerate
    ('{"summary": "legacy format"}', 0),                     # auto-upgrade of old cache: free
])
def test_c6_pipeline_summary_regenerate_is_charged(db_session, test_tenant, monkeypatch, existing, charged):
    from app.services.pipeline_summary import generate_pipeline_summary
    adapter = MagicMock()
    adapter._call_api.return_value = '{"summary": "AI", "suggestions": [], "highlights": []}'
    monkeypatch.setattr("app.services.warmup.content_generator.get_ai_adapter", lambda *a, **k: adapter)
    run = _finished_run(db_session, test_tenant.tenant_id, existing)
    assert generate_pipeline_summary(db_session, run)["ai_generated"] is True
    assert len(_usage(db_session, test_tenant.tenant_id, "ai_suggestion")) == charged


def _clients(db, tenant_id, n):
    from app.db.models.client import ClientInfo
    rows = [ClientInfo(tenant_id=tenant_id, client_name=f"Co {i}") for i in range(n)]
    db.add_all(rows)
    db.commit()
    return [r.client_id for r in rows]


def test_c6_bulk_company_enrich_capped_at_100(client, db_session, test_tenant, auth_headers, monkeypatch):
    import app.api.endpoints.clients as clients_ep
    monkeypatch.setattr(clients_ep, "bulk_enrich_clients", lambda *a, **k: {"enriched": 0})
    r = client.post("/api/v1/clients/bulk/enrich", headers=auth_headers,
                    json={"client_ids": list(range(1, 102))})
    assert r.status_code == 400


def test_c6_bulk_company_enrich_is_gated_without_metering_twice(client, db_session, test_tenant, auth_headers, monkeypatch):
    import app.api.endpoints.clients as clients_ep
    calls = []
    monkeypatch.setattr(clients_ep, "bulk_enrich_clients",
                        lambda db, ids, tenant_id=None: calls.append(ids) or {"enriched": len(ids)})
    ids = _clients(db_session, test_tenant.tenant_id, 5)
    _enforce(monkeypatch)
    _set_available(db_session, test_tenant.tenant_id, 14)  # 5 x 3 = 15 needed
    r = client.post("/api/v1/clients/bulk/enrich", headers=auth_headers, json={"client_ids": ids})
    assert r.status_code == 402 and calls == []

    _set_available(db_session, test_tenant.tenant_id, 15)
    r = client.post("/api/v1/clients/bulk/enrich", headers=auth_headers, json={"client_ids": ids})
    assert r.status_code == 200, r.text
    assert _usage(db_session, test_tenant.tenant_id) == []  # metering is company_enrichment's job


def test_c6_single_company_enrich_is_gated(client, db_session, test_tenant, auth_headers, monkeypatch):
    import app.api.endpoints.clients as clients_ep
    monkeypatch.setattr(clients_ep, "enrich_client", lambda *a, **k: {"enriched": True})
    (cid,) = _clients(db_session, test_tenant.tenant_id, 1)
    _enforce(monkeypatch)
    _set_available(db_session, test_tenant.tenant_id, 2)
    r = client.post(f"/api/v1/clients/{cid}/enrich", headers=auth_headers)
    assert r.status_code == 402


def test_c6_new_actions_are_priced():
    assert CREDIT_COSTS["ai_suggestion"].credits == 1
    assert CREDIT_COSTS["ai_classification"].credits == 0.5
    assert CREDIT_COSTS["ai_classification"].category == "ai"
