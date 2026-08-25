"""Invoice-number sequence integrity (ELR-010).

The old MAX(string LIKE) generator mis-ordered across digit widths and could
collide/abort under concurrent generation. The counter-backed generator is
gapless and seeds from any pre-existing invoices so it never reuses a number.
"""
import pytest
from datetime import date

from app.services.billing.invoice_generator import _generate_invoice_number
from app.db.models.invoice import Invoice, InvoiceStatus

pytestmark = pytest.mark.unit


def test_sequence_is_gapless(db_session):
    year = date.today().year
    nums = [_generate_invoice_number(db_session) for _ in range(3)]
    db_session.commit()
    assert nums == [f"INV-{year}-0001", f"INV-{year}-0002", f"INV-{year}-0003"]


def test_numbers_are_unique(db_session):
    nums = [_generate_invoice_number(db_session) for _ in range(25)]
    db_session.commit()
    assert len(set(nums)) == 25


def test_seeds_from_existing_invoices_no_collision(db_session, test_tenant):
    year = date.today().year
    # A legacy invoice issued before the sequence table existed.
    db_session.add(Invoice(
        tenant_id=test_tenant.tenant_id, invoice_number=f"INV-{year}-0007",
        period_start=date(year, 1, 1), period_end=date(year, 1, 31),
        due_date=date(year, 2, 5), subtotal_cents=1, tax_cents=0, total_cents=1,
        status=InvoiceStatus.SENT,
    ))
    db_session.commit()
    n = _generate_invoice_number(db_session)
    db_session.commit()
    assert n == f"INV-{year}-0008"  # continues past legacy 0007, no reuse
