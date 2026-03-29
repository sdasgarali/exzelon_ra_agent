import math
from datetime import date, datetime
from typing import Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func, extract
import structlog

logger = structlog.get_logger()


def _generate_invoice_number(db: Session) -> str:
    """Generate next invoice number INV-YYYY-NNNN (sequential per year)."""
    from app.db.models.invoice import Invoice
    current_year = date.today().year
    # Get max invoice number for current year
    last = db.query(func.max(Invoice.invoice_number)).filter(
        Invoice.invoice_number.like(f"INV-{current_year}-%")
    ).scalar()
    if last:
        seq = int(last.split("-")[-1]) + 1
    else:
        seq = 1
    return f"INV-{current_year}-{seq:04d}"


def get_billing_period(ref_date: date = None) -> Tuple[date, date]:
    """Get billing period (1st to last day of the month)."""
    import calendar
    if ref_date is None:
        ref_date = date.today()
    first_day = ref_date.replace(day=1)
    last_day_num = calendar.monthrange(ref_date.year, ref_date.month)[1]
    last_day = ref_date.replace(day=last_day_num)
    return first_day, last_day


def format_cents(cents: int) -> str:
    """Format cents as dollar string: 29900 -> '$299.00'."""
    return f"${cents / 100:,.2f}"


def generate_invoice_for_tenant(
    db: Session,
    tenant_id: int,
    period_start: date,
    period_end: date,
    override_amount_cents: Optional[int] = None,
    created_by: str = "system",
) -> dict:
    """Generate a single invoice for a tenant.

    Returns dict with keys: status ('created'/'skipped'/'error'), invoice_id, invoice_number, detail
    """
    from app.db.models.tenant import Tenant
    from app.db.models.invoice import Invoice, InvoiceLineItem, InvoiceStatus, LineItemType
    from app.core.config import settings

    try:
        tenant = db.query(Tenant).filter(Tenant.tenant_id == tenant_id).first()
        if not tenant:
            return {"status": "error", "detail": f"Tenant {tenant_id} not found"}

        amount_cents = override_amount_cents if override_amount_cents is not None else tenant.monthly_price_cents
        if amount_cents <= 0:
            return {"status": "skipped", "detail": "No billing amount (free tenant)"}

        # Check for duplicate (same tenant + period)
        existing = db.query(Invoice).filter(
            Invoice.tenant_id == tenant_id,
            Invoice.period_start == period_start,
            Invoice.period_end == period_end,
            Invoice.is_archived == False,
        ).first()
        if existing:
            return {"status": "skipped", "detail": f"Invoice already exists: {existing.invoice_number}",
                    "invoice_id": existing.invoice_id, "invoice_number": existing.invoice_number}

        # Calculate tax
        tax_rate = float(tenant.tax_rate_percent or 0)
        if tax_rate <= 0:
            tax_rate = settings.BILLING_TAX_RATE_DEFAULT
        tax_cents = math.ceil(amount_cents * tax_rate / 100) if tax_rate > 0 else 0
        total_cents = amount_cents + tax_cents

        # Generate invoice number
        invoice_number = _generate_invoice_number(db)

        # Due date
        due_date = period_start.replace(day=min(settings.INVOICE_DUE_DAY, 28))

        # Create invoice
        invoice = Invoice(
            tenant_id=tenant_id,
            invoice_number=invoice_number,
            period_start=period_start,
            period_end=period_end,
            due_date=due_date,
            subtotal_cents=amount_cents,
            tax_cents=tax_cents,
            total_cents=total_cents,
            currency="USD",
            status=InvoiceStatus.DRAFT,
        )
        db.add(invoice)
        db.flush()  # Get invoice_id

        # Create line items
        plan_name = tenant.plan.value.title() if tenant.plan else "Subscription"
        period_label = period_start.strftime("%B %Y")
        db.add(InvoiceLineItem(
            invoice_id=invoice.invoice_id,
            description=f"{plan_name} Plan - {period_label}",
            quantity=1,
            unit_price_cents=amount_cents,
            total_cents=amount_cents,
            item_type=LineItemType.SUBSCRIPTION,
        ))

        if tax_cents > 0:
            db.add(InvoiceLineItem(
                invoice_id=invoice.invoice_id,
                description=f"Tax ({tax_rate}%)",
                quantity=1,
                unit_price_cents=tax_cents,
                total_cents=tax_cents,
                item_type=LineItemType.TAX,
            ))

        # Generate PDF
        try:
            from app.services.billing.pdf_generator import generate_invoice_pdf
            line_items = db.query(InvoiceLineItem).filter(
                InvoiceLineItem.invoice_id == invoice.invoice_id
            ).all()
            pdf_path = generate_invoice_pdf(invoice, line_items, tenant)
            invoice.pdf_path = pdf_path
        except Exception as e:
            logger.warning("PDF generation failed", invoice_number=invoice_number, error=str(e))

        # Mark as sent
        invoice.status = InvoiceStatus.SENT

        # Audit log
        try:
            from app.db.models.audit_log import AuditLog
            db.add(AuditLog(
                tenant_id=tenant_id,
                entity_type="invoice",
                entity_id=invoice.invoice_id,
                action="invoice_created",
                changed_by=created_by,
                notes=f"Invoice {invoice_number} created for {format_cents(total_cents)}",
            ))
        except Exception:
            pass

        db.commit()

        # Send email (after commit so invoice is persisted)
        try:
            from app.services.billing.billing_mailer import send_new_invoice_email
            send_new_invoice_email(invoice, tenant)
        except Exception as e:
            logger.warning("Invoice email failed", invoice_number=invoice_number, error=str(e))

        logger.info("Invoice generated", invoice_number=invoice_number,
                    tenant_id=tenant_id, total=format_cents(total_cents))

        return {
            "status": "created",
            "invoice_id": invoice.invoice_id,
            "invoice_number": invoice_number,
            "total_cents": total_cents,
        }

    except Exception as e:
        db.rollback()
        logger.error("Invoice generation failed", tenant_id=tenant_id, error=str(e))
        return {"status": "error", "detail": str(e)}


def bulk_generate_invoices(
    db: Session,
    tenant_ids: list,
    period_start: date,
    period_end: date,
    created_by: str = "system",
) -> dict:
    """Generate invoices for multiple tenants."""
    results = {"generated": 0, "skipped": 0, "errors": 0, "details": []}
    for tid in tenant_ids:
        result = generate_invoice_for_tenant(db, tid, period_start, period_end, created_by=created_by)
        results["details"].append({"tenant_id": tid, **result})
        if result["status"] == "created":
            results["generated"] += 1
        elif result["status"] == "skipped":
            results["skipped"] += 1
        else:
            results["errors"] += 1
    logger.info("Bulk invoice generation complete",
                generated=results["generated"], skipped=results["skipped"], errors=results["errors"])
    return results
