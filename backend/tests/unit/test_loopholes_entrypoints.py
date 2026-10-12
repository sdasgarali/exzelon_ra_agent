"""Regression tests for the entry-point loopholes closed in Plan_Credit_Loopholes.md (Agent B).

Each test reproduces an abuse path that was open on decc862 and asserts it is now
blocked. Grouped by plan item (B1..B8).
"""
import json

import pytest

from app.db.models.settings import Settings
from app.db.models.tenant_settings import TenantSettings

pytestmark = pytest.mark.unit

API = "/api/v1"


def _tenant_value(db_session, tenant_id, key):
    row = db_session.query(TenantSettings).filter(
        TenantSettings.tenant_id == tenant_id, TenantSettings.key == key,
    ).first()
    return None if row is None else json.loads(row.value_json)


@pytest.fixture
def admin_full_settings(db_session):
    """Give tenant admins full access to every settings tab (as production does),
    so the tests exercise the new guards rather than the tab-permission check."""
    db_session.add(Settings(key="role_permissions", type="json", value_json=json.dumps({
        "admin": {"settings": "full"}, "bdm": {"settings": "read"}, "recruiter": {"settings": "no_access"},
    })))
    db_session.commit()


# ---------------------------------------------------------------------------
# B1 — PUT /settings/{key}: platform-controlled keys + safe business-rule ranges
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("admin_full_settings")
class TestB1SettingsLockdown:

    @pytest.mark.parametrize("key,value", [
        ("credit_enforcement_enabled", False),
        ("feature_email_validation_enabled", False),
        ("feature_campaigns_enabled", True),
        ("feature_outreach_enabled", True),
        ("credit_anything", 1),
    ])
    def test_tenant_admin_cannot_set_platform_keys(self, client, db_session, auth_headers, test_tenant, key, value):
        r = client.put(f"{API}/settings/{key}", headers=auth_headers, json={"value": value})
        assert r.status_code == 403, r.text
        assert _tenant_value(db_session, test_tenant.tenant_id, key) is None

    def test_super_admin_can_set_platform_key_for_tenant(self, client, db_session, sa_headers, test_tenant):
        headers = {**sa_headers, "X-Tenant-ID": str(test_tenant.tenant_id)}
        r = client.put(f"{API}/settings/feature_campaigns_enabled", headers=headers, json={"value": False})
        assert r.status_code == 200, r.text
        assert _tenant_value(db_session, test_tenant.tenant_id, "feature_campaigns_enabled") is False

    def test_tenant_admin_cannot_clear_platform_override(self, client, db_session, auth_headers, test_tenant):
        # Super admin disabled campaigns for this tenant; deleting the override
        # would fall back to the global default (enabled).
        db_session.add(TenantSettings(tenant_id=test_tenant.tenant_id, key="feature_campaigns_enabled",
                                      value_json=json.dumps(False)))
        db_session.commit()
        r = client.delete(f"{API}/settings/feature_campaigns_enabled/tenant-override", headers=auth_headers)
        assert r.status_code == 403, r.text
        assert _tenant_value(db_session, test_tenant.tenant_id, "feature_campaigns_enabled") is False

    @pytest.mark.parametrize("key,value", [
        ("cooldown_days", 0),
        ("cooldown_days", -5),
        ("cooldown_days", 366),
        ("max_contacts_per_company_job", 999),
        ("max_contacts_per_company_job", 0),
        ("daily_send_limit", 10_000),
        ("daily_send_limit", 0),
        ("cooldown_days", "abc"),
    ])
    def test_tenant_admin_business_rules_out_of_range_rejected(self, client, db_session, auth_headers, test_tenant, key, value):
        r = client.put(f"{API}/settings/{key}", headers=auth_headers, json={"value": value})
        assert r.status_code == 400, r.text
        assert _tenant_value(db_session, test_tenant.tenant_id, key) is None

    @pytest.mark.parametrize("key,value", [
        ("cooldown_days", 14),
        ("max_contacts_per_company_job", 1),
        ("daily_send_limit", 25),
    ])
    def test_tenant_admin_business_rules_in_range_accepted(self, client, db_session, auth_headers, test_tenant, key, value):
        r = client.put(f"{API}/settings/{key}", headers=auth_headers, json={"value": value})
        assert r.status_code == 200, r.text
        assert _tenant_value(db_session, test_tenant.tenant_id, key) == value

    def test_value_json_path_is_validated_too(self, client, auth_headers):
        r = client.put(f"{API}/settings/cooldown_days", headers=auth_headers, json={"value_json": "0"})
        assert r.status_code == 400

    def test_super_admin_global_business_rule_not_range_limited(self, client, sa_headers):
        r = client.put(f"{API}/settings/daily_send_limit", headers=sa_headers, json={"value": 100})
        assert r.status_code == 200, r.text

    def test_write_scoped_api_key_cannot_write_settings(self):
        from app.core.api_key_scopes import check_scope
        assert check_scope(["write"], "PUT", "/api/v1/settings/cooldown_days")[0] is False
        assert check_scope(["admin"], "PUT", "/api/v1/settings/cooldown_days")[0] is True


# ---------------------------------------------------------------------------
# B2 — is_test / validation_status are super-admin-only on contacts
# ---------------------------------------------------------------------------

def _make_contact(db_session, tenant_id, email="b2@acme-corp.com", **kw):
    from app.db.models.contact import ContactDetails
    c = ContactDetails(tenant_id=tenant_id, client_name="Acme", first_name="Ann",
                       last_name="Lee", email=email, **kw)
    db_session.add(c)
    db_session.commit()
    db_session.refresh(c)
    return c


class TestB2ContactBypassFields:

    def test_admin_cannot_create_test_contact(self, client, auth_headers):
        r = client.post(f"{API}/contacts", headers=auth_headers, json={
            "client_name": "Acme", "first_name": "A", "last_name": "B",
            "email": "t1@acme-corp.com", "is_test": True})
        assert r.status_code == 403, r.text

    def test_bdm_cannot_create_test_contact(self, client, operator_headers):
        r = client.post(f"{API}/contacts", headers=operator_headers, json={
            "client_name": "Acme", "first_name": "A", "last_name": "B",
            "email": "t2@acme-corp.com", "is_test": True})
        assert r.status_code == 403, r.text

    def test_admin_can_create_normal_contact(self, client, auth_headers):
        r = client.post(f"{API}/contacts", headers=auth_headers, json={
            "client_name": "Acme", "first_name": "A", "last_name": "B",
            "email": "t3@acme-corp.com", "is_test": False})
        assert r.status_code == 201, r.text
        assert r.json()["is_test"] is False

    def test_admin_cannot_flip_is_test(self, client, db_session, auth_headers, test_tenant):
        c = _make_contact(db_session, test_tenant.tenant_id)
        r = client.put(f"{API}/contacts/{c.contact_id}", headers=auth_headers, json={"is_test": True})
        assert r.status_code == 403, r.text
        db_session.refresh(c)
        assert c.is_test is False

    def test_admin_cannot_mark_contact_valid(self, client, db_session, auth_headers, test_tenant):
        c = _make_contact(db_session, test_tenant.tenant_id, validation_status=None)
        r = client.put(f"{API}/contacts/{c.contact_id}", headers=auth_headers,
                       json={"validation_status": "valid"})
        assert r.status_code == 403, r.text
        db_session.refresh(c)
        assert c.validation_status is None

    def test_admin_echoing_unchanged_values_is_allowed(self, client, db_session, auth_headers, test_tenant):
        c = _make_contact(db_session, test_tenant.tenant_id, validation_status="valid")
        r = client.put(f"{API}/contacts/{c.contact_id}", headers=auth_headers,
                       json={"title": "HR Director", "is_test": False, "validation_status": "valid"})
        assert r.status_code == 200, r.text
        assert r.json()["title"] == "HR Director"

    def test_admin_email_change_cannot_carry_valid_status(self, client, db_session, auth_headers, test_tenant):
        c = _make_contact(db_session, test_tenant.tenant_id, validation_status="valid")
        r = client.put(f"{API}/contacts/{c.contact_id}", headers=auth_headers,
                       json={"email": "other@acme-corp.com", "validation_status": "valid"})
        assert r.status_code == 200, r.text
        assert r.json()["validation_status"] is None

    def test_admin_can_clear_validation_status(self, client, db_session, auth_headers, test_tenant):
        """Clearing only makes a contact less sendable, so it stays allowed. The MCP
        connector's update_contact clears it with an email change (its e2e suite
        caught this)."""
        c = _make_contact(db_session, test_tenant.tenant_id, validation_status="valid")
        r = client.put(f"{API}/contacts/{c.contact_id}", headers=auth_headers,
                       json={"email": "moved@acme-corp.com", "validation_status": None})
        assert r.status_code == 200, r.text
        assert r.json()["validation_status"] is None
        r = client.put(f"{API}/contacts/{c.contact_id}", headers=auth_headers,
                       json={"validation_status": None})
        assert r.status_code == 200, r.text

    def test_super_admin_can_set_bypass_fields(self, client, db_session, sa_headers, test_tenant):
        c = _make_contact(db_session, test_tenant.tenant_id)
        r = client.put(f"{API}/contacts/{c.contact_id}", headers=sa_headers,
                       json={"is_test": True, "validation_status": "valid"})
        assert r.status_code == 200, r.text
        assert r.json()["is_test"] is True and r.json()["validation_status"] == "valid"


# ---------------------------------------------------------------------------
# B3 — /leads/database-search is budget-gated and metered
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_apollo(monkeypatch):
    calls = []

    class _FakeApollo:
        def __init__(self, *a, **k):
            pass

        def search_contacts(self, company_name, job_title=None, state=None, limit=25, **k):
            calls.append(limit)
            return [{"first_name": f"P{i}", "last_name": "X", "email": f"p{i}@acme-corp.com"}
                    for i in range(min(limit, 4))]

    import app.services.adapters.contact_discovery.apollo as apollo_mod
    monkeypatch.setattr(apollo_mod, "ApolloAdapter", _FakeApollo)
    return calls


class TestB3DatabaseSearch:

    def test_results_are_metered_and_committed(self, client, db_session, auth_headers, test_tenant, fake_apollo):
        from app.db.models.credit_usage import CreditUsage
        from app.core.credit_costs import cost_for
        r = client.post(f"{API}/leads/database-search", headers=auth_headers,
                        json={"company": "Acme Manufacturing", "job_title": "HR Manager", "limit": 10})
        assert r.status_code == 200, r.text
        assert r.json()["count"] == 4
        db_session.expire_all()
        rows = db_session.query(CreditUsage).filter(
            CreditUsage.tenant_id == test_tenant.tenant_id,
            CreditUsage.usage_type == "contact_enriched",
        ).all()
        assert len(rows) == 1
        assert rows[0].credits_used == pytest.approx(cost_for("contact_enriched", 4))

    def test_budget_gate_uses_worst_case_and_blocks(self, client, auth_headers, fake_apollo, monkeypatch):
        from fastapi import HTTPException
        import app.services.credit_metering as cm
        seen = {}

        def _deny(db, tenant_id, plan=None, credits_needed=1.0):
            seen["needed"] = credits_needed
            raise HTTPException(status_code=402, detail="Out of credits")

        monkeypatch.setattr(cm, "check_credit_budget", _deny)
        r = client.post(f"{API}/leads/database-search", headers=auth_headers,
                        json={"company": "Acme Manufacturing", "limit": 20})
        assert r.status_code == 402
        from app.core.credit_costs import cost_for
        assert seen["needed"] == pytest.approx(20 * cost_for("contact_enriched"))
        assert fake_apollo == []  # provider never called

    def test_suspended_tenant_blocked(self, client, db_session, auth_headers, test_tenant, fake_apollo):
        test_tenant.billing_suspended = True
        db_session.commit()
        r = client.post(f"{API}/leads/database-search", headers=auth_headers,
                        json={"company": "Acme Manufacturing"})
        assert r.status_code == 402
        assert fake_apollo == []

    def test_super_admin_without_tenant_is_not_metered(self, client, db_session, sa_headers, fake_apollo):
        from app.db.models.credit_usage import CreditUsage
        r = client.post(f"{API}/leads/database-search", headers=sa_headers,
                        json={"company": "Acme Manufacturing", "limit": 5})
        assert r.status_code == 200, r.text
        assert db_session.query(CreditUsage).count() == 0

    def test_read_scoped_api_key_cannot_call_it(self):
        from app.core.api_key_scopes import check_scope
        assert check_scope(["read"], "POST", "/api/v1/leads/database-search")[0] is False


# ---------------------------------------------------------------------------
# B4 — CSV / Google-Sheet import: role, row cap, plan limits
# ---------------------------------------------------------------------------

def _csv(n, with_email=True):
    lines = ["Company Name,Job Title,State,Job Link,Email,First Name,Last Name"]
    for i in range(n):
        email = f"hr{i}@acme{i}-mfg.com" if with_email else ""
        lines.append(f"Acme Manufacturing {i},Plant Manager,TX,https://jobs.example.com/b4-{i},{email},Pat,Doe")
    return "\n".join(lines) + "\n"


def _upload(client, headers, n):
    return client.post(f"{API}/leads/import/csv", headers=headers,
                       files={"file": ("leads.csv", _csv(n).encode(), "text/csv")})


@pytest.fixture
def fake_sheet(monkeypatch):
    import app.api.endpoints.leads as leads_mod
    state = {"n": 3, "fetched": 0}

    async def _fetch(sheet_id, gid):
        state["fetched"] += 1
        return _csv(state["n"])

    monkeypatch.setattr(leads_mod, "_fetch_google_sheet_csv", _fetch)
    return state


SHEET = {"sheet_url": "https://docs.google.com/spreadsheets/d/abcDEF123/edit"}


class TestB4Imports:

    def test_recruiter_cannot_import_csv(self, client, db_session, viewer_headers):
        from app.db.models.lead import LeadDetails
        r = _upload(client, viewer_headers, 2)
        assert r.status_code == 403, r.text
        assert db_session.query(LeadDetails).count() == 0

    def test_recruiter_cannot_import_google_sheet(self, client, viewer_headers, fake_sheet):
        r = client.post(f"{API}/leads/import/google-sheet", headers=viewer_headers, json=SHEET)
        assert r.status_code == 403, r.text
        assert fake_sheet["fetched"] == 0

    def test_admin_csv_import_still_works(self, client, auth_headers):
        r = _upload(client, auth_headers, 2)
        assert r.status_code == 200, r.text
        assert r.json()["imported"] == 2

    def test_row_cap(self, client, auth_headers, monkeypatch):
        from app.core.config import settings as app_settings
        monkeypatch.setattr(app_settings, "MAX_IMPORT_ROWS", 3)
        r = _upload(client, auth_headers, 4)
        assert r.status_code == 413, r.text

    def test_default_row_cap_is_5000(self):
        from app.core.config import Settings
        assert Settings.model_fields["MAX_IMPORT_ROWS"].default == 5000

    def test_csv_import_stops_at_plan_lead_limit(self, client, db_session, professional_admin_headers,
                                                 professional_capped_tenant):
        from app.db.models.lead import LeadDetails
        from app.db.models.contact import ContactDetails
        r = _upload(client, professional_admin_headers, 5)  # plan: max_leads=3, max_contacts=2
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["imported"] == 3
        assert body["plan_limited"] == 2
        tid = professional_capped_tenant.tenant_id
        assert db_session.query(LeadDetails).filter(LeadDetails.tenant_id == tid).count() == 3
        assert db_session.query(ContactDetails).filter(ContactDetails.tenant_id == tid).count() == 2

    def test_import_refused_when_already_at_plan_limit(self, client, db_session, professional_admin_headers,
                                                       professional_capped_tenant):
        from datetime import date
        from app.db.models.lead import LeadDetails, LeadStatus
        for i in range(3):
            db_session.add(LeadDetails(tenant_id=professional_capped_tenant.tenant_id, client_name=f"X{i}",
                                       job_title="Plant Manager", state="TX", posting_date=date.today(),
                                       lead_status=LeadStatus.NEW))
        db_session.commit()
        r = _upload(client, professional_admin_headers, 1)
        assert r.status_code == 403, r.text

    def test_google_sheet_import_respects_plan_limit(self, client, professional_admin_headers, fake_sheet):
        fake_sheet["n"] = 5
        r = client.post(f"{API}/leads/import/google-sheet", headers=professional_admin_headers, json=SHEET)
        assert r.status_code == 200, r.text
        assert r.json()["imported"] == 3


# ---------------------------------------------------------------------------
# B5 — send gate: billing suspension + tenant-scoped validation; rule clamping
# ---------------------------------------------------------------------------

def _set_tenant_rule(db_session, tenant_id, key, value):
    db_session.add(TenantSettings(tenant_id=tenant_id, key=key, value_json=json.dumps(value)))
    db_session.commit()


class TestB5SendGate:

    def test_suspended_tenant_blocked_for_every_send_mode(self, db_session, test_tenant):
        from app.services.send_gate import unified_send_gate
        c = _make_contact(db_session, test_tenant.tenant_id, validation_status="valid")
        test_tenant.billing_suspended = True
        db_session.commit()
        for kwargs in ({}, {"dry_run": True}, {"is_reply": True}):
            res = unified_send_gate(db_session, c, test_tenant.tenant_id, **kwargs)
            assert not res.allowed, kwargs
            assert res.reason_code == "BILLING_SUSPENDED"

    def test_active_tenant_not_blocked_by_billing_check(self, db_session, test_tenant):
        from app.services.send_gate import unified_send_gate
        c = _make_contact(db_session, test_tenant.tenant_id, validation_status="valid")
        res = unified_send_gate(db_session, c, test_tenant.tenant_id, dry_run=True)
        assert next(ch for ch in res.checks if ch.name == "billing").passed

    def test_other_tenants_validation_result_does_not_validate_contact(self, db_session, test_tenant):
        from datetime import datetime
        from app.db.models.email_validation import EmailValidationResult, ValidationStatus
        from app.services.send_gate import unified_send_gate
        # A postal address is required for outreach (CAN-SPAM) — give the workspace
        # one so the validation check is what's exercised.
        test_tenant.company_address = "1 Main St, Springfield"
        # Some other tenant paid to validate this address; this tenant never did.
        db_session.add(EmailValidationResult(email="shared@acme-corp.com", provider="neverbounce",
                                             status=ValidationStatus.VALID, validated_at=datetime.utcnow()))
        c = _make_contact(db_session, test_tenant.tenant_id, email="shared@acme-corp.com", validation_status=None)
        res = unified_send_gate(db_session, c, test_tenant.tenant_id, dry_run=True)
        assert not res.allowed
        assert res.reason_code == "INVALID_EMAIL"

    def test_stale_zero_cooldown_override_is_clamped(self, db_session, test_tenant):
        from app.services.send_gate import _resolve_cooldown_days
        _set_tenant_rule(db_session, test_tenant.tenant_id, "cooldown_days", 0)
        assert _resolve_cooldown_days(db_session, test_tenant.tenant_id) == 1

    def test_stale_huge_contact_cap_override_is_clamped(self, db_session, test_tenant):
        from app.core.config import settings as app_settings
        from app.services.send_gate import _resolve_max_contacts_per_lead
        _set_tenant_rule(db_session, test_tenant.tenant_id, "max_contacts_per_company_job", 999)
        assert _resolve_max_contacts_per_lead(db_session, test_tenant.tenant_id) == \
            app_settings.MAX_CONTACTS_PER_COMPANY_PER_JOB

    def test_global_super_admin_value_raises_the_ceiling(self, db_session, test_tenant):
        from app.services.send_gate import _resolve_max_contacts_per_lead
        db_session.add(Settings(key="max_contacts_per_company_job", type="integer", value_json="4"))
        db_session.commit()
        _set_tenant_rule(db_session, test_tenant.tenant_id, "max_contacts_per_company_job", 999)
        assert _resolve_max_contacts_per_lead(db_session, test_tenant.tenant_id) == 4


# ---------------------------------------------------------------------------
# B7 — mailbox daily_send_limit bound + outreach pipeline clamping
# ---------------------------------------------------------------------------

class TestB7DailySendLimit:

    def test_mailbox_create_schema_rejects_huge_limit(self):
        from pydantic import ValidationError
        from app.schemas.sender_mailbox import SenderMailboxCreate
        with pytest.raises(ValidationError):
            SenderMailboxCreate(email="s@acme-corp.com", daily_send_limit=10_000)
        with pytest.raises(ValidationError):
            SenderMailboxCreate(email="s@acme-corp.com", daily_send_limit=0)
        assert SenderMailboxCreate(email="s@acme-corp.com", daily_send_limit=50).daily_send_limit == 50

    def test_mailbox_update_schema_rejects_huge_limit(self):
        from pydantic import ValidationError
        from app.schemas.sender_mailbox import SenderMailboxUpdate
        with pytest.raises(ValidationError):
            SenderMailboxUpdate(daily_send_limit=500)
        assert SenderMailboxUpdate(daily_send_limit=None).daily_send_limit is None

    def test_update_mailbox_endpoint_rejects_huge_limit(self, client, auth_headers, sample_mailbox):
        r = client.put(f"{API}/mailboxes/{sample_mailbox.mailbox_id}", headers=auth_headers,
                       json={"daily_send_limit": 5000})
        assert r.status_code == 422, r.text

    def test_response_schema_still_serialises_legacy_rows(self, db_session, sample_mailbox):
        from app.schemas.sender_mailbox import SenderMailboxResponse
        sample_mailbox.daily_send_limit = 400
        db_session.commit()
        assert SenderMailboxResponse.model_validate(sample_mailbox).daily_send_limit == 400

    def test_outreach_business_rules_are_clamped(self, db_session, test_tenant):
        from app.core.config import settings as app_settings
        from app.services.pipelines.outreach import resolve_business_rules
        _set_tenant_rule(db_session, test_tenant.tenant_id, "daily_send_limit", 10_000)
        _set_tenant_rule(db_session, test_tenant.tenant_id, "cooldown_days", 0)
        rules = resolve_business_rules(db_session, tenant_id=test_tenant.tenant_id)
        assert rules["daily_send_limit"] == app_settings.MAX_DAILY_SEND_LIMIT_PER_MAILBOX
        assert rules["cooldown_days"] == 1

    def test_sendable_mailboxes_respect_platform_cap(self, db_session, test_tenant, sample_mailbox):
        from app.services.pipelines.outreach import sendable_mailboxes_query
        sample_mailbox.daily_send_limit = 400
        sample_mailbox.emails_sent_today = 60  # over the 50 platform cap
        db_session.commit()
        assert sendable_mailboxes_query(db_session, test_tenant.tenant_id).count() == 0


# ---------------------------------------------------------------------------
# B6 — signup: email validation/normalisation, alias duplicates, disposable
#       domains, shared rate-limit storage
# ---------------------------------------------------------------------------

def _signup(client, email):
    from unittest.mock import patch
    with patch("app.services.email_verification._send_email", return_value=True):
        return client.post(f"{API}/auth/signup", json={
            "email": email, "password": "SecurePass123!",
            "full_name": "Jane Doe", "company_name": f"Co {email}", "accept_terms": True,
        })


class TestB6Signup:

    def test_invalid_email_rejected(self, client, db_session):
        assert _signup(client, "not-an-email").status_code == 422

    def test_email_stored_lowercase(self, client, db_session):
        from app.db.models.user import User
        r = _signup(client, "  New.User@Startup-Co.com ")
        assert r.status_code == 201, r.text
        assert db_session.query(User).filter(User.email == "new.user@startup-co.com").count() == 1

    @pytest.mark.parametrize("first,second", [
        ("dup@startup-co.com", "DUP@Startup-Co.com"),
        ("jane@acme-io.com", "jane+promo@acme-io.com"),
        ("jane+a@acme-io.com", "jane+b@acme-io.com"),
        ("janedoe@gmail.com", "j.ane.doe+x@googlemail.com"),
    ])
    def test_alias_of_existing_user_rejected(self, client, db_session, first, second):
        assert _signup(client, first).status_code == 201
        r = _signup(client, second)
        assert r.status_code == 400, r.text
        assert "already registered" in r.json()["detail"]

    def test_dots_are_significant_outside_gmail(self, client, db_session):
        assert _signup(client, "jane.doe@acme-io.com").status_code == 201
        assert _signup(client, "janedoe@acme-io.com").status_code == 201

    @pytest.mark.parametrize("email", ["x@mailinator.com", "x@YOPMAIL.com", "x@eu.guerrillamail.com"])
    def test_disposable_domain_rejected(self, client, db_session, email):
        r = _signup(client, email)
        assert r.status_code == 400, r.text

    def test_configured_blocked_domain_rejected(self, client, db_session, monkeypatch):
        from app.core.config import settings as app_settings
        monkeypatch.setattr(app_settings, "BLOCKED_SIGNUP_DOMAINS", "burner-example.org, other.test")
        assert _signup(client, "x@burner-example.org").status_code == 400

    def test_normalize_mailbox(self):
        from app.api.endpoints.auth import normalize_mailbox
        assert normalize_mailbox("J.Doe+tag@GoogleMail.com") == "jdoe@gmail.com"
        assert normalize_mailbox("a.b+c@corp.com") == "a.b@corp.com"

    def test_rate_limit_storage_configurable(self, monkeypatch):
        from app.core.config import settings as app_settings
        import app.core.rate_limiter as rl
        monkeypatch.setattr(app_settings, "RATE_LIMIT_STORAGE_URI", "")
        assert rl._storage_uri() == "memory://"
        monkeypatch.setattr(app_settings, "RATE_LIMIT_STORAGE_URI", "redis://localhost:6379/0")
        assert rl._storage_uri() == "redis://localhost:6379/0"


# ---------------------------------------------------------------------------
# B8 — notification sender test-send: own address only + rate limit
# ---------------------------------------------------------------------------

@pytest.fixture
def stub_test_send(monkeypatch):
    import app.api.endpoints.settings as settings_ep
    sent = []

    def _send(db, tenant_id, to):
        sent.append(to)
        return True, "Sent."

    monkeypatch.setattr(settings_ep, "send_test_email", _send)
    return sent


class TestB8NotificationTestSend:

    def test_admin_cannot_send_to_arbitrary_address(self, client, auth_headers, stub_test_send):
        r = client.post(f"{API}/settings/notifications/sender/test", headers=auth_headers,
                        json={"to_email": "victim@elsewhere-corp.com"})
        assert r.status_code == 403, r.text
        assert stub_test_send == []

    def test_admin_can_send_to_own_address(self, client, auth_headers, stub_test_send):
        r = client.post(f"{API}/settings/notifications/sender/test", headers=auth_headers,
                        json={"to_email": "Admin@Test.com"})
        assert r.status_code == 200, r.text
        assert stub_test_send == ["Admin@Test.com"]

    def test_super_admin_may_send_anywhere(self, client, sa_headers, test_tenant, stub_test_send):
        headers = {**sa_headers, "X-Tenant-ID": str(test_tenant.tenant_id)}
        r = client.post(f"{API}/settings/notifications/sender/test", headers=headers,
                        json={"to_email": "ops@elsewhere-corp.com"})
        assert r.status_code == 200, r.text

    def test_rate_limited(self, client, auth_headers, stub_test_send):
        from app.core.rate_limiter import limiter
        limiter.enabled = True
        try:
            limiter._storage.reset()
            codes = [
                client.post(f"{API}/settings/notifications/sender/test", headers=auth_headers,
                            json={"to_email": "admin@test.com"}).status_code
                for _ in range(6)
            ]
        finally:
            limiter.enabled = False
            limiter._storage.reset()
        assert codes[:5] == [200] * 5
        assert codes[5] == 429
        assert len(stub_test_send) == 5
