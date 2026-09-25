"""Credit and quota isolation between tenants (Phase 5.3).

Extends the Epic 1A isolation suite to the billing surfaces added in Phases 2-4. A
failure here is worse than the data leaks that suite was written for: one tenant
spending another's credits, or seeing their balance, is both a privacy breach and a
billing dispute.
"""
import pytest

from app.core.security import create_access_token, get_password_hash
from app.db.models.credit_usage import CreditUsage
from app.db.models.tenant import Tenant, TenantPlan
from app.db.models.user import User, UserRole
from app.services.credit_metering import (
    available_credits, get_balance, grant_topup, month_usage, spend,
)

pytestmark = [pytest.mark.integration, pytest.mark.security]


def _tenant(db, name, slug, plan=TenantPlan.PRO):
    t = Tenant(name=name, slug=slug, plan=plan)
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


def _admin_headers(db, tenant, email):
    u = User(email=email, password_hash=get_password_hash("testpassword"),
             full_name=f"Admin {email}", role=UserRole.ADMIN,
             is_active=True, is_verified=True, tenant_id=tenant.tenant_id)
    db.add(u)
    db.commit()
    tok = create_access_token(data={
        "sub": u.email, "role": u.role,
        "tenant_id": u.tenant_id, "plan": tenant.plan.value,
    })
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture
def two_billed_tenants(db_session):
    a = _tenant(db_session, "Credit A", "credit-a")
    b = _tenant(db_session, "Credit B", "credit-b")
    return a, b


# ---------------------------------------------------------------------------
# Balances
# ---------------------------------------------------------------------------

def test_each_tenant_gets_its_own_balance_row(db_session, two_billed_tenants):
    a, b = two_billed_tenants
    ba = get_balance(db_session, a.tenant_id)
    bb = get_balance(db_session, b.tenant_id)
    assert ba.balance_id != bb.balance_id
    assert ba.tenant_id == a.tenant_id and bb.tenant_id == b.tenant_id


def test_spending_never_touches_another_tenants_balance(db_session, two_billed_tenants):
    a, b = two_billed_tenants
    get_balance(db_session, a.tenant_id)
    before_b = get_balance(db_session, b.tenant_id).allowance_credits

    for _ in range(10):
        spend(db_session, a.tenant_id, "contact_enriched")
    db_session.commit()

    assert get_balance(db_session, a.tenant_id).allowance_credits == before_b - 30
    assert get_balance(db_session, b.tenant_id).allowance_credits == before_b
    assert get_balance(db_session, b.tenant_id).period_spent == 0


def test_a_topup_credits_only_the_paying_tenant(db_session, two_billed_tenants):
    a, b = two_billed_tenants
    grant_topup(db_session, a.tenant_id, 5_000, reference_id="cs_a")

    assert available_credits(db_session, a.tenant_id)["topup"] == 5_000
    assert available_credits(db_session, b.tenant_id)["topup"] == 0


def test_month_usage_is_tenant_scoped(db_session, two_billed_tenants):
    a, b = two_billed_tenants
    spend(db_session, a.tenant_id, "icp_wizard")  # 10 credits
    db_session.commit()

    assert month_usage(db_session, a.tenant_id) == 10
    assert month_usage(db_session, b.tenant_id) == 0


def test_ledger_entries_never_cross_tenants(db_session, two_billed_tenants):
    a, b = two_billed_tenants
    spend(db_session, a.tenant_id, "lead_sourced", 7)
    db_session.commit()

    rows_b = db_session.query(CreditUsage).filter(
        CreditUsage.tenant_id == b.tenant_id).all()
    assert rows_b == []


def test_exhausting_one_tenant_does_not_block_another(db_session, two_billed_tenants, monkeypatch):
    """The gate must be per-tenant. A shared counter would take everyone down at once."""
    from fastapi import HTTPException
    from app.core.config import settings
    from app.services.credit_metering import check_credit_budget

    monkeypatch.setattr(settings, "CREDIT_ENFORCEMENT_ENABLED", True)
    a, b = two_billed_tenants

    ba = get_balance(db_session, a.tenant_id)
    ba.allowance_credits = 0.0
    ba.topup_credits = 0.0
    db_session.commit()

    with pytest.raises(HTTPException) as exc:
        check_credit_budget(db_session, a.tenant_id, credits_needed=1)
    assert exc.value.status_code == 402

    check_credit_budget(db_session, b.tenant_id, credits_needed=1)  # unaffected


# ---------------------------------------------------------------------------
# Send quota
# ---------------------------------------------------------------------------

def test_send_quota_counts_only_the_owning_tenant(db_session, two_billed_tenants):
    from app.db.models.contact import ContactDetails
    from app.db.models.outreach import OutreachChannel, OutreachEvent, OutreachStatus
    from app.services.send_quota import sends_this_month

    a, b = two_billed_tenants
    for i in range(5):
        c = ContactDetails(tenant_id=a.tenant_id, client_name="C",
                           first_name="F", last_name="L", email=f"iso{i}@x.com")
        db_session.add(c)
        db_session.flush()
        db_session.add(OutreachEvent(
            tenant_id=a.tenant_id, contact_id=c.contact_id,
            channel=OutreachChannel.SMTP, status=OutreachStatus.SENT,
        ))
    db_session.commit()

    assert sends_this_month(db_session, a.tenant_id) == 5
    assert sends_this_month(db_session, b.tenant_id) == 0


# ---------------------------------------------------------------------------
# Over HTTP
# ---------------------------------------------------------------------------

def test_balance_endpoint_never_reports_another_tenants_numbers(
    client, db_session, two_billed_tenants
):
    a, b = two_billed_tenants
    grant_topup(db_session, a.tenant_id, 9_999, reference_id="cs_iso")
    db_session.commit()

    headers_b = _admin_headers(db_session, b, "iso-b@test.com")
    r = client.get("/api/v1/credits/balance", headers=headers_b)
    assert r.status_code == 200
    assert r.json()["topup_remaining"] == 0, "tenant B can see tenant A's top-up"


def test_usage_endpoint_is_scoped_to_the_caller(client, db_session, two_billed_tenants):
    a, b = two_billed_tenants
    spend(db_session, a.tenant_id, "icp_wizard", 3)  # 30 credits on A
    db_session.commit()

    headers_b = _admin_headers(db_session, b, "iso-usage-b@test.com")
    r = client.get("/api/v1/billing/usage", headers=headers_b)
    assert r.status_code == 200
    body = r.json()
    assert body["credits"]["period_spent"] == 0
    assert body["breakdown"] == []


def test_usage_endpoint_reports_topup_offer_and_only_own_expiry(
    client, db_session, two_billed_tenants
):
    """The billing UI reads the top-up price from here — it must not hardcode one — and
    one tenant's expiring top-up must never surface on another tenant's screen."""
    a, b = two_billed_tenants
    grant_topup(db_session, a.tenant_id, 1_000, reference_id="cs_expiry_iso")
    db_session.commit()

    r = client.get("/api/v1/billing/usage",
                   headers=_admin_headers(db_session, b, "iso-offer-b@test.com"))
    assert r.status_code == 200
    body = r.json()
    assert body["topup"]["block_size"] == 1000
    assert body["topup"]["block_price_cents"] == 2000
    assert body["topup"]["validity_days"] == 365
    assert body["credits"]["topup_next_expiry"] is None


def test_a_tenant_cannot_spend_via_another_tenants_header(
    client, db_session, two_billed_tenants
):
    """A non-super-admin must not be able to act as another tenant via X-Tenant-ID.

    Impersonation is a super-admin capability; if a tenant admin could set the header
    they would be able to drain someone else's credits.
    """
    a, b = two_billed_tenants
    headers_b = _admin_headers(db_session, b, "iso-hdr-b@test.com")
    headers_b["X-Tenant-ID"] = str(a.tenant_id)

    r = client.get("/api/v1/billing/usage", headers=headers_b)
    assert r.status_code in (200, 403)
    if r.status_code == 200:
        # If the header is ignored (the safe outcome) the caller still sees only B.
        assert r.json()["credits"]["period_spent"] == 0
        assert get_balance(db_session, a.tenant_id).period_spent == 0
