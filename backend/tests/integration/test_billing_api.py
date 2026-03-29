"""Integration tests for billing API endpoints."""
import pytest
from datetime import date, datetime

pytestmark = pytest.mark.integration


@pytest.fixture
def billable_tenant(db_session, test_tenant):
    """Make test_tenant billable with a price."""
    test_tenant.monthly_price_cents = 29900
    test_tenant.tax_rate_percent = 0
    test_tenant.billing_email = "billing@test.com"
    db_session.commit()
    return test_tenant


@pytest.fixture
def sample_invoice(db_session, billable_tenant):
    """Create a sample invoice for testing."""
    from app.db.models.invoice import Invoice, InvoiceLineItem, InvoiceStatus, LineItemType
    inv = Invoice(
        tenant_id=billable_tenant.tenant_id,
        invoice_number="INV-2026-0001",
        period_start=date(2026, 3, 1),
        period_end=date(2026, 3, 31),
        due_date=date(2026, 3, 5),
        subtotal_cents=29900,
        tax_cents=0,
        total_cents=29900,
        status=InvoiceStatus.SENT,
    )
    db_session.add(inv)
    db_session.flush()
    db_session.add(InvoiceLineItem(
        invoice_id=inv.invoice_id,
        description="Enterprise Plan - March 2026",
        quantity=1,
        unit_price_cents=29900,
        total_cents=29900,
        item_type=LineItemType.SUBSCRIPTION,
    ))
    db_session.commit()
    db_session.refresh(inv)
    return inv


@pytest.fixture
def second_tenant(db_session):
    """Create a second tenant for isolation tests."""
    from app.db.models.tenant import Tenant, TenantPlan
    t = Tenant(
        name="Other Corp",
        slug="other-corp",
        plan=TenantPlan.PROFESSIONAL,
        monthly_price_cents=19900,
        max_users=10,
    )
    db_session.add(t)
    db_session.commit()
    db_session.refresh(t)
    return t


@pytest.fixture
def second_tenant_invoice(db_session, second_tenant):
    """Create an invoice for the second tenant."""
    from app.db.models.invoice import Invoice, InvoiceStatus
    inv = Invoice(
        tenant_id=second_tenant.tenant_id,
        invoice_number="INV-2026-0002",
        period_start=date(2026, 3, 1),
        period_end=date(2026, 3, 31),
        due_date=date(2026, 3, 5),
        subtotal_cents=19900,
        tax_cents=0,
        total_cents=19900,
        status=InvoiceStatus.SENT,
    )
    db_session.add(inv)
    db_session.commit()
    db_session.refresh(inv)
    return inv


# ─── Super Admin Tests ────────────────────────────────────────────────────────


class TestSuperAdminListInvoices:
    def test_list_all_invoices(self, client, sa_headers, sample_invoice):
        r = client.get("/api/v1/billing/invoices", headers=sa_headers)
        assert r.status_code == 200
        data = r.json()
        assert "invoices" in data
        assert data["total"] >= 1

    def test_filter_by_status(self, client, sa_headers, sample_invoice):
        r = client.get("/api/v1/billing/invoices?status=sent", headers=sa_headers)
        assert r.status_code == 200
        for inv in r.json()["invoices"]:
            assert inv["status"] == "sent"

    def test_filter_by_tenant(self, client, sa_headers, sample_invoice, second_tenant_invoice):
        tid = sample_invoice.tenant_id
        r = client.get(f"/api/v1/billing/invoices?tenant_id={tid}", headers=sa_headers)
        assert r.status_code == 200
        for inv in r.json()["invoices"]:
            assert inv["tenant_id"] == tid


class TestSuperAdminBulkGenerate:
    def test_bulk_generate(self, client, sa_headers, billable_tenant):
        r = client.post("/api/v1/billing/invoices/bulk-generate", headers=sa_headers, json={
            "tenant_ids": [billable_tenant.tenant_id],
            "period_start": "2026-04-01",
            "period_end": "2026-04-30",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["generated"] == 1

    def test_bulk_generate_skip_free(self, client, sa_headers, db_session):
        from app.db.models.tenant import Tenant, TenantPlan
        free = Tenant(name="Free", slug="free-co", plan=TenantPlan.STARTER,
                     monthly_price_cents=0, max_users=3)
        db_session.add(free)
        db_session.commit()

        r = client.post("/api/v1/billing/invoices/bulk-generate", headers=sa_headers, json={
            "tenant_ids": [free.tenant_id],
            "period_start": "2026-04-01",
            "period_end": "2026-04-30",
        })
        assert r.status_code == 200
        assert r.json()["skipped"] == 1


class TestSuperAdminMarkPaid:
    def test_mark_paid(self, client, sa_headers, sample_invoice):
        r = client.put(f"/api/v1/billing/invoices/{sample_invoice.invoice_id}/mark-paid",
                      headers=sa_headers, json={
            "payment_method": "manual",
            "reference": "CHK-12345",
            "notes": "Paid by check",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["invoice"]["status"] == "paid"
        assert data["payment"]["payment_method"] == "manual"

    def test_mark_paid_already_paid(self, client, sa_headers, sample_invoice, db_session):
        from app.db.models.invoice import InvoiceStatus
        sample_invoice.status = InvoiceStatus.PAID
        db_session.commit()

        r = client.put(f"/api/v1/billing/invoices/{sample_invoice.invoice_id}/mark-paid",
                      headers=sa_headers, json={
            "payment_method": "manual",
        })
        assert r.status_code == 400

    def test_mark_paid_invalid_method(self, client, sa_headers, sample_invoice):
        r = client.put(f"/api/v1/billing/invoices/{sample_invoice.invoice_id}/mark-paid",
                      headers=sa_headers, json={
            "payment_method": "bitcoin",
        })
        assert r.status_code == 400

    def test_mark_paid_not_found(self, client, sa_headers):
        r = client.put("/api/v1/billing/invoices/99999/mark-paid",
                      headers=sa_headers, json={"payment_method": "manual"})
        assert r.status_code == 404


class TestSuperAdminSoftDelete:
    def test_soft_delete(self, client, sa_headers, sample_invoice):
        r = client.delete(f"/api/v1/billing/invoices/{sample_invoice.invoice_id}", headers=sa_headers)
        assert r.status_code == 200
        assert "deleted" in r.json()["message"].lower()

    def test_soft_delete_not_found(self, client, sa_headers):
        r = client.delete("/api/v1/billing/invoices/99999", headers=sa_headers)
        assert r.status_code == 404


class TestSuperAdminPayments:
    def test_list_payments(self, client, sa_headers):
        r = client.get("/api/v1/billing/payments", headers=sa_headers)
        assert r.status_code == 200
        assert "payments" in r.json()


class TestSuperAdminStats:
    def test_billing_stats(self, client, sa_headers, sample_invoice):
        r = client.get("/api/v1/billing/stats", headers=sa_headers)
        assert r.status_code == 200
        data = r.json()
        assert "total_outstanding_cents" in data
        assert "collected_this_month_cents" in data
        assert "overdue_count" in data
        assert "mrr_cents" in data
        assert data["total_outstanding_cents"] >= 29900


# ─── Tenant User Tests ────────────────────────────────────────────────────────


class TestTenantMyInvoices:
    def test_list_own_invoices(self, client, auth_headers, sample_invoice):
        r = client.get("/api/v1/billing/my-invoices", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["total"] >= 1
        for inv in data["invoices"]:
            assert inv["tenant_id"] == sample_invoice.tenant_id

    def test_cannot_see_other_tenant(self, client, auth_headers, second_tenant_invoice):
        """Tenant admin should NOT see another tenant's invoices."""
        r = client.get("/api/v1/billing/my-invoices", headers=auth_headers)
        assert r.status_code == 200
        ids = [i["invoice_id"] for i in r.json()["invoices"]]
        assert second_tenant_invoice.invoice_id not in ids

    def test_invoice_detail(self, client, auth_headers, sample_invoice):
        r = client.get(f"/api/v1/billing/my-invoices/{sample_invoice.invoice_id}", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["invoice_number"] == "INV-2026-0001"
        assert "line_items" in data

    def test_invoice_detail_other_tenant_404(self, client, auth_headers, second_tenant_invoice):
        """Should return 404 for another tenant's invoice."""
        r = client.get(f"/api/v1/billing/my-invoices/{second_tenant_invoice.invoice_id}", headers=auth_headers)
        assert r.status_code == 404


class TestTenantMyPayments:
    def test_list_own_payments(self, client, auth_headers):
        r = client.get("/api/v1/billing/my-payments", headers=auth_headers)
        assert r.status_code == 200
        assert "payments" in r.json()


# ─── RBAC Tests ───────────────────────────────────────────────────────────────


class TestBillingRBAC:
    def test_viewer_cannot_access_my_invoices(self, client, viewer_headers):
        r = client.get("/api/v1/billing/my-invoices", headers=viewer_headers)
        assert r.status_code == 403

    def test_admin_cannot_access_super_admin_routes(self, client, auth_headers):
        r = client.get("/api/v1/billing/invoices", headers=auth_headers)
        assert r.status_code == 403

    def test_admin_cannot_bulk_generate(self, client, auth_headers):
        r = client.post("/api/v1/billing/invoices/bulk-generate", headers=auth_headers, json={
            "tenant_ids": [1],
            "period_start": "2026-04-01",
            "period_end": "2026-04-30",
        })
        assert r.status_code == 403

    def test_admin_cannot_mark_paid(self, client, auth_headers, sample_invoice):
        r = client.put(f"/api/v1/billing/invoices/{sample_invoice.invoice_id}/mark-paid",
                      headers=auth_headers, json={"payment_method": "manual"})
        assert r.status_code == 403

    def test_operator_can_view_invoices(self, client, operator_headers, sample_invoice):
        r = client.get("/api/v1/billing/my-invoices", headers=operator_headers)
        assert r.status_code == 200

    def test_unauthenticated_cannot_access(self, client):
        r = client.get("/api/v1/billing/my-invoices")
        assert r.status_code == 401


class TestOverrideAmount:
    def test_override_sent_invoice(self, client, sa_headers, sample_invoice):
        r = client.put(f"/api/v1/billing/invoices/{sample_invoice.invoice_id}/override-amount",
                      headers=sa_headers, json={
            "new_amount_cents": 19900,
            "reason": "Discount applied",
        })
        assert r.status_code == 200
        assert r.json()["invoice"]["subtotal_cents"] == 19900

    def test_cannot_override_paid(self, client, sa_headers, sample_invoice, db_session):
        from app.db.models.invoice import InvoiceStatus
        sample_invoice.status = InvoiceStatus.PAID
        db_session.commit()

        r = client.put(f"/api/v1/billing/invoices/{sample_invoice.invoice_id}/override-amount",
                      headers=sa_headers, json={
            "new_amount_cents": 19900,
            "reason": "Too late",
        })
        assert r.status_code == 400
