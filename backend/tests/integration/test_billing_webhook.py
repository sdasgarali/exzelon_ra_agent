"""Stripe webhook idempotency + verification (ELR-008).

Guards the money path: a replayed event must not double-record a payment, and a
payment whose amount/tenant doesn't match the invoice must be refused.
"""
import pytest
from datetime import date

from app.db.models.invoice import Invoice, InvoiceStatus, PaymentRecord, ProcessedStripeEvent

pytestmark = pytest.mark.integration


def _make_invoice(db, tenant_id, total_cents=10000, status=InvoiceStatus.SENT):
    inv = Invoice(
        tenant_id=tenant_id, invoice_number="INV-2026-9001",
        period_start=date(2026, 1, 1), period_end=date(2026, 1, 31),
        due_date=date(2026, 2, 5), subtotal_cents=total_cents, tax_cents=0,
        total_cents=total_cents, currency="USD", status=status,
    )
    db.add(inv)
    db.commit()
    db.refresh(inv)
    return inv


def _configure_stripe(monkeypatch, event):
    """Make the webhook think Stripe is configured and return `event`."""
    from app.core.config import settings
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test", raising=False)
    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", "whsec_test", raising=False)
    import stripe
    monkeypatch.setattr(stripe.Webhook, "construct_event", lambda *a, **k: event, raising=True)


def _checkout_event(event_id, invoice, amount=None, tenant_id=None):
    return {
        "id": event_id,
        "type": "checkout.session.completed",
        "data": {"object": {
            "id": "cs_1",
            "payment_intent": "pi_1",
            "amount_total": invoice.total_cents if amount is None else amount,
            "metadata": {
                "invoice_id": str(invoice.invoice_id),
                "tenant_id": str(tenant_id if tenant_id is not None else invoice.tenant_id),
            },
        }},
    }


def _post(client):
    return client.post("/api/v1/billing/webhook/stripe", content=b"{}",
                       headers={"stripe-signature": "t=1,v1=x"})


def test_webhook_marks_invoice_paid(client, db_session, test_tenant, monkeypatch):
    inv = _make_invoice(db_session, test_tenant.tenant_id, 10000)
    _configure_stripe(monkeypatch, _checkout_event("evt_pay", inv))
    r = _post(client)
    assert r.status_code == 200
    db_session.expire_all()
    inv2 = db_session.query(Invoice).get(inv.invoice_id)
    assert inv2.status == InvoiceStatus.PAID
    assert db_session.query(PaymentRecord).filter_by(invoice_id=inv.invoice_id).count() == 1
    assert db_session.query(ProcessedStripeEvent).filter_by(event_id="evt_pay").count() == 1


def test_webhook_replay_is_idempotent(client, db_session, test_tenant, monkeypatch):
    inv = _make_invoice(db_session, test_tenant.tenant_id, 10000)
    _configure_stripe(monkeypatch, _checkout_event("evt_dup", inv))
    r1 = _post(client)
    r2 = _post(client)  # same event id, replayed
    assert r1.status_code == 200 and r2.status_code == 200
    assert r2.json().get("duplicate") is True
    db_session.expire_all()
    # Exactly one payment despite two deliveries.
    assert db_session.query(PaymentRecord).filter_by(invoice_id=inv.invoice_id).count() == 1


def test_webhook_amount_mismatch_refused(client, db_session, test_tenant, monkeypatch):
    inv = _make_invoice(db_session, test_tenant.tenant_id, 10000)
    _configure_stripe(monkeypatch, _checkout_event("evt_bad_amt", inv, amount=500))
    r = _post(client)
    assert r.status_code == 400
    db_session.expire_all()
    inv2 = db_session.query(Invoice).get(inv.invoice_id)
    assert inv2.status == InvoiceStatus.SENT  # not marked paid
    assert db_session.query(PaymentRecord).filter_by(invoice_id=inv.invoice_id).count() == 0


def test_webhook_tenant_mismatch_refused(client, db_session, test_tenant, monkeypatch):
    inv = _make_invoice(db_session, test_tenant.tenant_id, 10000)
    _configure_stripe(monkeypatch, _checkout_event("evt_bad_tenant", inv, tenant_id=99999))
    r = _post(client)
    assert r.status_code == 400
    db_session.expire_all()
    inv2 = db_session.query(Invoice).get(inv.invoice_id)
    assert inv2.status == InvoiceStatus.SENT


def test_webhook_invalid_signature_400(client, db_session, test_tenant, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test", raising=False)
    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", "whsec_test", raising=False)
    import stripe

    def _raise(*a, **k):
        raise stripe.error.SignatureVerificationError("bad", "sig")
    monkeypatch.setattr(stripe.Webhook, "construct_event", _raise, raising=True)
    r = _post(client)
    assert r.status_code == 400
