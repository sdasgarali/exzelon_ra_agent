"""Billing lifecycle: tax rounding + currency (ELR-029), refund/failed-payment
webhook handling (ELR-022), and suspend-on-nonpayment (ELR-023)."""
import pytest
from datetime import date

from app.services.billing.invoice_generator import compute_tax_cents
from app.db.models.invoice import Invoice, InvoiceStatus, PaymentRecord, PaymentStatus

pytestmark = pytest.mark.integration


def _invoice(db, tenant_id, status=InvoiceStatus.PAID, pi="pi_1", total=10000):
    inv = Invoice(
        tenant_id=tenant_id, invoice_number="INV-2026-8001",
        period_start=date(2026, 1, 1), period_end=date(2026, 1, 31),
        due_date=date(2026, 2, 5), subtotal_cents=total, tax_cents=0,
        total_cents=total, currency="USD", status=status,
        stripe_payment_intent_id=pi,
    )
    db.add(inv)
    db.commit()
    db.refresh(inv)
    return inv


def _configure_stripe(monkeypatch, event):
    from app.core.config import settings
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test", raising=False)
    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", "whsec_test", raising=False)
    import stripe
    monkeypatch.setattr(stripe.Webhook, "construct_event", lambda *a, **k: event, raising=True)


def _post(client):
    return client.post("/api/v1/billing/webhook/stripe", content=b"{}",
                       headers={"stripe-signature": "x"})


# ---- ELR-029: tax rounding + currency ----

def test_tax_rounds_half_up_not_ceil():
    assert compute_tax_cents(101, 10) == 10   # 10.1 -> 10 (ceil would give 11)
    assert compute_tax_cents(105, 10) == 11   # 10.5 -> 11
    assert compute_tax_cents(10000, 8.25) == 825
    assert compute_tax_cents(10000, 0) == 0


def test_invoice_uses_configured_currency(db_session, test_tenant, monkeypatch):
    from app.core.config import settings
    from app.services.billing.invoice_generator import generate_invoice_for_tenant
    monkeypatch.setattr(settings, "BILLING_DEFAULT_CURRENCY", "EUR")
    test_tenant.monthly_price_cents = 5000
    db_session.commit()
    res = generate_invoice_for_tenant(db_session, test_tenant.tenant_id,
                                      date(2026, 3, 1), date(2026, 3, 31))
    assert res["status"] == "created"
    inv = db_session.query(Invoice).get(res["invoice_id"])
    assert inv.currency == "EUR"


# ---- ELR-022: refund / failed-payment webhook ----

def test_webhook_refund_marks_invoice_refunded(client, db_session, test_tenant, monkeypatch):
    inv = _invoice(db_session, test_tenant.tenant_id, status=InvoiceStatus.PAID, pi="pi_ref")
    _configure_stripe(monkeypatch, {
        "id": "evt_ref", "type": "charge.refunded",
        "data": {"object": {"payment_intent": "pi_ref", "amount_refunded": 10000}},
    })
    r = _post(client)
    assert r.status_code == 200
    db_session.expire_all()
    inv2 = db_session.query(Invoice).get(inv.invoice_id)
    assert inv2.status == InvoiceStatus.REFUNDED
    refunds = db_session.query(PaymentRecord).filter_by(
        invoice_id=inv.invoice_id, status=PaymentStatus.REFUNDED).all()
    assert len(refunds) == 1 and refunds[0].amount_cents == -10000


def test_webhook_payment_failed_marks_overdue(client, db_session, test_tenant, monkeypatch):
    inv = _invoice(db_session, test_tenant.tenant_id, status=InvoiceStatus.SENT, pi="pi_fail")
    _configure_stripe(monkeypatch, {
        "id": "evt_fail", "type": "payment_intent.payment_failed",
        "data": {"object": {"id": "pi_fail"}},
    })
    r = _post(client)
    assert r.status_code == 200
    db_session.expire_all()
    assert db_session.query(Invoice).get(inv.invoice_id).status == InvoiceStatus.OVERDUE


# ---- ELR-023: suspend-on-nonpayment ----

@pytest.mark.asyncio
async def test_require_tenant_id_blocks_suspended(db_session, test_tenant):
    from app.api.deps.auth import require_tenant_id
    from fastapi import HTTPException
    test_tenant.billing_suspended = True
    db_session.commit()
    with pytest.raises(HTTPException) as exc:
        await require_tenant_id(db=db_session, tenant_id=test_tenant.tenant_id)
    assert exc.value.status_code == 402


@pytest.mark.asyncio
async def test_require_tenant_id_allows_unsuspended(db_session, test_tenant):
    from app.api.deps.auth import require_tenant_id
    assert await require_tenant_id(db=db_session, tenant_id=test_tenant.tenant_id) == test_tenant.tenant_id


def test_clear_suspension_when_settled(db_session, test_tenant):
    from app.api.endpoints.billing import _clear_suspension_if_settled
    test_tenant.billing_suspended = True
    db_session.commit()
    # No unpaid invoices → suspension lifts.
    _clear_suspension_if_settled(db_session, test_tenant.tenant_id)
    db_session.commit()
    db_session.refresh(test_tenant)
    assert test_tenant.billing_suspended is False


def test_clear_suspension_kept_when_unpaid_remains(db_session, test_tenant):
    from app.api.endpoints.billing import _clear_suspension_if_settled
    test_tenant.billing_suspended = True
    _invoice(db_session, test_tenant.tenant_id, status=InvoiceStatus.OVERDUE, pi="pi_z")
    _clear_suspension_if_settled(db_session, test_tenant.tenant_id)
    db_session.commit()
    db_session.refresh(test_tenant)
    assert test_tenant.billing_suspended is True  # still owes
