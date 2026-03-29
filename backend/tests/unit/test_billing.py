"""Unit tests for billing services."""
import pytest
from datetime import date, datetime
from unittest.mock import patch, MagicMock

pytestmark = pytest.mark.unit


class TestInvoiceNumberGeneration:
    """Tests for invoice number format and sequencing."""

    def test_first_invoice_of_year(self, db_session):
        """First invoice should be INV-YYYY-0001."""
        from app.services.billing.invoice_generator import _generate_invoice_number
        number = _generate_invoice_number(db_session)
        year = date.today().year
        assert number == f"INV-{year}-0001"

    def test_sequential_numbering(self, db_session):
        """Invoice numbers should increment sequentially."""
        from app.services.billing.invoice_generator import _generate_invoice_number
        from app.db.models.invoice import Invoice, InvoiceStatus
        year = date.today().year

        # Create a few invoices
        for i in range(1, 4):
            inv = Invoice(
                tenant_id=1,
                invoice_number=f"INV-{year}-{i:04d}",
                period_start=date(year, 1, 1),
                period_end=date(year, 1, 31),
                due_date=date(year, 1, 5),
                subtotal_cents=10000,
                tax_cents=0,
                total_cents=10000,
                status=InvoiceStatus.SENT,
            )
            db_session.add(inv)
        db_session.commit()

        number = _generate_invoice_number(db_session)
        assert number == f"INV-{year}-0004"

    def test_zero_padded(self, db_session):
        """Numbers should be zero-padded to 4 digits."""
        from app.services.billing.invoice_generator import _generate_invoice_number
        number = _generate_invoice_number(db_session)
        seq_part = number.split("-")[-1]
        assert len(seq_part) == 4
        assert seq_part == "0001"


class TestBillingPeriod:
    """Tests for billing period calculation."""

    def test_january(self):
        from app.services.billing.invoice_generator import get_billing_period
        start, end = get_billing_period(date(2026, 1, 15))
        assert start == date(2026, 1, 1)
        assert end == date(2026, 1, 31)

    def test_february_non_leap(self):
        from app.services.billing.invoice_generator import get_billing_period
        start, end = get_billing_period(date(2025, 2, 10))
        assert start == date(2025, 2, 1)
        assert end == date(2025, 2, 28)

    def test_february_leap_year(self):
        from app.services.billing.invoice_generator import get_billing_period
        start, end = get_billing_period(date(2028, 2, 10))
        assert start == date(2028, 2, 1)
        assert end == date(2028, 2, 29)

    def test_defaults_to_current_month(self):
        from app.services.billing.invoice_generator import get_billing_period
        start, end = get_billing_period()
        today = date.today()
        assert start.month == today.month
        assert start.year == today.year
        assert start.day == 1


class TestFormatCents:
    """Tests for cents formatting."""

    def test_whole_dollars(self):
        from app.services.billing.invoice_generator import format_cents
        assert format_cents(29900) == "$299.00"

    def test_with_cents(self):
        from app.services.billing.invoice_generator import format_cents
        assert format_cents(32367) == "$323.67"

    def test_zero(self):
        from app.services.billing.invoice_generator import format_cents
        assert format_cents(0) == "$0.00"

    def test_large_amount(self):
        from app.services.billing.invoice_generator import format_cents
        result = format_cents(1234567)
        assert "12,345.67" in result


class TestInvoiceGeneration:
    """Tests for generate_invoice_for_tenant."""

    def test_skips_free_tenant(self, db_session, test_tenant):
        """Should skip tenants with monthly_price_cents=0."""
        from app.services.billing.invoice_generator import generate_invoice_for_tenant
        test_tenant.monthly_price_cents = 0
        db_session.commit()

        result = generate_invoice_for_tenant(
            db_session, test_tenant.tenant_id,
            date(2026, 3, 1), date(2026, 3, 31),
        )
        assert result["status"] == "skipped"
        assert "free" in result["detail"].lower()

    def test_creates_invoice(self, db_session, test_tenant):
        """Should create an invoice with correct amounts."""
        from app.services.billing.invoice_generator import generate_invoice_for_tenant
        test_tenant.monthly_price_cents = 29900
        test_tenant.tax_rate_percent = 0
        db_session.commit()

        result = generate_invoice_for_tenant(
            db_session, test_tenant.tenant_id,
            date(2026, 3, 1), date(2026, 3, 31),
        )
        assert result["status"] == "created"
        assert result["total_cents"] == 29900
        assert "INV-" in result["invoice_number"]

    def test_prevents_duplicate(self, db_session, test_tenant):
        """Should not create duplicate invoice for same period."""
        from app.services.billing.invoice_generator import generate_invoice_for_tenant
        test_tenant.monthly_price_cents = 29900
        db_session.commit()

        # First invoice
        r1 = generate_invoice_for_tenant(
            db_session, test_tenant.tenant_id,
            date(2026, 3, 1), date(2026, 3, 31),
        )
        assert r1["status"] == "created"

        # Duplicate attempt
        r2 = generate_invoice_for_tenant(
            db_session, test_tenant.tenant_id,
            date(2026, 3, 1), date(2026, 3, 31),
        )
        assert r2["status"] == "skipped"
        assert "already exists" in r2["detail"].lower()

    def test_with_tax(self, db_session, test_tenant):
        """Should calculate tax correctly."""
        from app.services.billing.invoice_generator import generate_invoice_for_tenant
        test_tenant.monthly_price_cents = 10000  # $100
        test_tenant.tax_rate_percent = 10  # 10%
        db_session.commit()

        result = generate_invoice_for_tenant(
            db_session, test_tenant.tenant_id,
            date(2026, 3, 1), date(2026, 3, 31),
        )
        assert result["status"] == "created"
        assert result["total_cents"] == 11000  # $100 + $10 tax

    def test_line_items_created(self, db_session, test_tenant):
        """Should create subscription + tax line items."""
        from app.services.billing.invoice_generator import generate_invoice_for_tenant
        from app.db.models.invoice import InvoiceLineItem
        test_tenant.monthly_price_cents = 10000
        test_tenant.tax_rate_percent = 8.25
        db_session.commit()

        result = generate_invoice_for_tenant(
            db_session, test_tenant.tenant_id,
            date(2026, 3, 1), date(2026, 3, 31),
        )
        assert result["status"] == "created"

        items = db_session.query(InvoiceLineItem).filter(
            InvoiceLineItem.invoice_id == result["invoice_id"]
        ).all()
        assert len(items) == 2  # subscription + tax
        types = [i.item_type.value for i in items]
        assert "subscription" in types
        assert "tax" in types

    def test_nonexistent_tenant(self, db_session):
        """Should return error for non-existent tenant."""
        from app.services.billing.invoice_generator import generate_invoice_for_tenant
        result = generate_invoice_for_tenant(
            db_session, 99999,
            date(2026, 3, 1), date(2026, 3, 31),
        )
        assert result["status"] == "error"


class TestBulkGeneration:
    """Tests for bulk_generate_invoices."""

    def test_bulk_multiple_tenants(self, db_session):
        """Should generate for multiple tenants and report results."""
        from app.services.billing.invoice_generator import bulk_generate_invoices
        from app.db.models.tenant import Tenant, TenantPlan

        # Create 2 tenants with billing, 1 free
        t1 = Tenant(name="T1", slug="t1", plan=TenantPlan.PROFESSIONAL,
                    monthly_price_cents=29900, max_users=10)
        t2 = Tenant(name="T2", slug="t2", plan=TenantPlan.ENTERPRISE,
                    monthly_price_cents=99900, max_users=10)
        t3 = Tenant(name="T3", slug="t3", plan=TenantPlan.STARTER,
                    monthly_price_cents=0, max_users=10)
        db_session.add_all([t1, t2, t3])
        db_session.commit()

        result = bulk_generate_invoices(
            db_session,
            [t1.tenant_id, t2.tenant_id, t3.tenant_id],
            date(2026, 4, 1), date(2026, 4, 30),
        )
        assert result["generated"] == 2
        assert result["skipped"] == 1


class TestPaymentGateway:
    """Tests for payment gateway factory."""

    def test_manual_gateway_when_no_stripe(self):
        """Should return ManualGateway when Stripe not configured."""
        from app.services.billing.payment_gateway import get_payment_gateway, ManualGateway
        with patch("app.core.config.settings") as mock_settings:
            mock_settings.STRIPE_SECRET_KEY = ""
            gw = get_payment_gateway()
            assert isinstance(gw, ManualGateway)

    def test_manual_gateway_checkout(self):
        """ManualGateway should return no checkout URL."""
        from app.services.billing.payment_gateway import ManualGateway
        gw = ManualGateway()
        result = gw.create_checkout_session(1, 10000, "USD", "test@test.com", "", "")
        assert result["checkout_url"] is None

    def test_manual_gateway_verify(self):
        """ManualGateway verify should return manual status."""
        from app.services.billing.payment_gateway import ManualGateway
        gw = ManualGateway()
        result = gw.verify_payment("test-id")
        assert result["status"] == "manual"

    def test_manual_gateway_create_customer(self):
        """ManualGateway should return prefixed customer ID."""
        from app.services.billing.payment_gateway import ManualGateway
        gw = ManualGateway()
        cid = gw.create_customer("test@test.com", "Test")
        assert cid == "manual_test@test.com"

    def test_manual_gateway_refund(self):
        """ManualGateway refund should return manual status."""
        from app.services.billing.payment_gateway import ManualGateway
        gw = ManualGateway()
        result = gw.refund_payment("test-id")
        assert result["status"] == "manual_refund"
