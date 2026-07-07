"""Billing & Invoicing API endpoints."""
from datetime import date, datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps.database import get_db
from app.api.deps.auth import get_current_active_user, require_role, get_current_tenant_id
from app.core.rate_limiter import limiter
from app.db.query_helpers import paginate
from app.db.models.user import UserRole

import structlog

logger = structlog.get_logger()

router = APIRouter(prefix="/billing", tags=["billing"])


# ─── Pydantic models ────────────────────────────────────────────────────────

class BulkGenerateRequest(BaseModel):
    tenant_ids: list[int] = Field(..., min_length=1)
    period_start: date
    period_end: date


class MarkPaidRequest(BaseModel):
    payment_method: str = Field(..., description="stripe/manual/bank_transfer/check/card")
    reference: str = Field(default="", max_length=255)
    notes: str = Field(default="")


class OverrideAmountRequest(BaseModel):
    new_amount_cents: int = Field(..., gt=0)
    reason: str = Field(..., min_length=1, max_length=500)


class PayRequest(BaseModel):
    success_url: str = Field(default="")
    cancel_url: str = Field(default="")


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _invoice_to_dict(inv) -> dict:
    return {
        "invoice_id": inv.invoice_id,
        "tenant_id": inv.tenant_id,
        "invoice_number": inv.invoice_number,
        "period_start": inv.period_start.isoformat() if inv.period_start else None,
        "period_end": inv.period_end.isoformat() if inv.period_end else None,
        "due_date": inv.due_date.isoformat() if inv.due_date else None,
        "subtotal_cents": inv.subtotal_cents,
        "tax_cents": inv.tax_cents,
        "total_cents": inv.total_cents,
        "currency": inv.currency,
        "status": inv.status.value if hasattr(inv.status, "value") else str(inv.status),
        "paid_at": inv.paid_at.isoformat() if inv.paid_at else None,
        "paid_via": inv.paid_via.value if inv.paid_via and hasattr(inv.paid_via, "value") else inv.paid_via,
        "payment_reference": inv.payment_reference,
        "stripe_invoice_id": inv.stripe_invoice_id,
        "notes": inv.notes,
        "pdf_path": inv.pdf_path,
        "reminder_count": inv.reminder_count,
        "last_reminder_at": inv.last_reminder_at.isoformat() if inv.last_reminder_at else None,
        "created_at": inv.created_at.isoformat() if inv.created_at else None,
        "is_archived": inv.is_archived,
    }


def _payment_to_dict(p) -> dict:
    return {
        "payment_id": p.payment_id,
        "tenant_id": p.tenant_id,
        "invoice_id": p.invoice_id,
        "amount_cents": p.amount_cents,
        "currency": p.currency,
        "payment_method": p.payment_method.value if hasattr(p.payment_method, "value") else str(p.payment_method),
        "reference": p.reference,
        "stripe_payment_id": p.stripe_payment_id,
        "status": p.status.value if hasattr(p.status, "value") else str(p.status),
        "recorded_by": p.recorded_by,
        "notes": p.notes,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


def _line_item_to_dict(li) -> dict:
    return {
        "line_id": li.line_id,
        "invoice_id": li.invoice_id,
        "description": li.description,
        "quantity": li.quantity,
        "unit_price_cents": li.unit_price_cents,
        "total_cents": li.total_cents,
        "item_type": li.item_type.value if hasattr(li.item_type, "value") else str(li.item_type),
    }


def _get_pdf_filepath(invoice) -> str:
    """Resolve absolute path to invoice PDF."""
    from pathlib import Path
    if not invoice.pdf_path:
        return None
    backend_dir = Path(__file__).resolve().parent.parent.parent.parent
    abs_path = backend_dir / invoice.pdf_path
    if abs_path.exists():
        return str(abs_path)
    return None


# ─── Super Admin Routes ──────────────────────────────────────────────────────

@router.get("/invoices")
def list_invoices(
    status_filter: Optional[str] = Query(None, alias="status"),
    tenant_id_filter: Optional[int] = Query(None, alias="tenant_id"),
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user=Depends(require_role([UserRole.SUPER_ADMIN])),
):
    """List all invoices (super admin only). Supports filtering by status, tenant, date range."""
    from app.db.models.invoice import Invoice, InvoiceStatus

    query = db.query(Invoice).filter(Invoice.is_archived == False)

    if status_filter:
        try:
            query = query.filter(Invoice.status == InvoiceStatus(status_filter))
        except ValueError:
            pass

    if tenant_id_filter:
        query = query.filter(Invoice.tenant_id == tenant_id_filter)

    if date_from:
        query = query.filter(Invoice.period_start >= date_from)
    if date_to:
        query = query.filter(Invoice.period_end <= date_to)

    query = query.order_by(Invoice.created_at.desc())
    result = paginate(query, page, page_size)

    return {
        "invoices": [_invoice_to_dict(i) for i in result["items"]],
        "total": result["total"],
        "page": result["page"],
        "page_size": result["page_size"],
        "pages": result["pages"],
    }


@router.post("/invoices/bulk-generate")
@limiter.limit("3/hour")
def bulk_generate(
    request: Request,
    req: BulkGenerateRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_role([UserRole.SUPER_ADMIN])),
):
    """Bulk generate invoices for selected tenants."""
    from app.services.billing.invoice_generator import bulk_generate_invoices
    result = bulk_generate_invoices(
        db, req.tenant_ids, req.period_start, req.period_end,
        created_by=current_user.email,
    )
    return result


@router.put("/invoices/{invoice_id}/mark-paid")
def mark_paid(
    invoice_id: int,
    req: MarkPaidRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_role([UserRole.SUPER_ADMIN])),
):
    """Mark an invoice as paid manually (creates PaymentRecord)."""
    from app.db.models.invoice import Invoice, InvoiceStatus, PaymentMethod, PaymentRecord, PaymentStatus
    from app.db.models.tenant import Tenant
    from app.db.models.audit_log import AuditLog

    invoice = db.query(Invoice).filter(
        Invoice.invoice_id == invoice_id,
        Invoice.is_archived == False,
    ).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if invoice.status == InvoiceStatus.PAID:
        raise HTTPException(status_code=400, detail="Invoice is already paid")

    # Validate payment method
    try:
        method = PaymentMethod(req.payment_method)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid payment method: {req.payment_method}")

    # Create payment record
    payment = PaymentRecord(
        tenant_id=invoice.tenant_id,
        invoice_id=invoice.invoice_id,
        amount_cents=invoice.total_cents,
        currency=invoice.currency,
        payment_method=method,
        reference=req.reference or None,
        status=PaymentStatus.SUCCEEDED,
        recorded_by=current_user.email,
        notes=req.notes or None,
    )
    db.add(payment)

    # Update invoice
    invoice.status = InvoiceStatus.PAID
    invoice.paid_at = datetime.utcnow()
    invoice.paid_via = method
    invoice.payment_reference = req.reference or None

    # Audit
    try:
        db.add(AuditLog(
            tenant_id=invoice.tenant_id,
            entity_type="invoice",
            entity_id=invoice.invoice_id,
            action="invoice_paid",
            changed_by=current_user.email,
            notes=f"Marked paid via {req.payment_method}. Ref: {req.reference}",
        ))
    except Exception as e_audit:
        logger.warning("Audit log failed for invoice_paid", error=str(e_audit))

    db.commit()

    # Send acknowledgement email
    try:
        tenant = db.query(Tenant).filter(Tenant.tenant_id == invoice.tenant_id).first()
        if tenant:
            from app.services.billing.billing_mailer import send_payment_acknowledgement_email
            send_payment_acknowledgement_email(invoice, tenant, payment)
    except Exception as e:
        logger.warning("Payment acknowledgement email failed", error=str(e))

    return {"message": "Invoice marked as paid", "invoice": _invoice_to_dict(invoice), "payment": _payment_to_dict(payment)}


@router.put("/invoices/{invoice_id}/override-amount")
def override_amount(
    invoice_id: int,
    req: OverrideAmountRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_role([UserRole.SUPER_ADMIN])),
):
    """Override invoice amount (draft/sent only)."""
    from app.db.models.invoice import Invoice, InvoiceStatus, InvoiceLineItem, LineItemType
    from app.db.models.audit_log import AuditLog

    invoice = db.query(Invoice).filter(
        Invoice.invoice_id == invoice_id,
        Invoice.is_archived == False,
    ).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if invoice.status not in (InvoiceStatus.DRAFT, InvoiceStatus.SENT):
        raise HTTPException(status_code=400, detail="Can only override draft or sent invoices")

    old_total = invoice.total_cents
    invoice.subtotal_cents = req.new_amount_cents

    # Recalculate tax
    from app.db.models.tenant import Tenant
    tenant = db.query(Tenant).filter(Tenant.tenant_id == invoice.tenant_id).first()
    tax_rate = float(tenant.tax_rate_percent or 0) if tenant else 0
    import math
    invoice.tax_cents = math.ceil(req.new_amount_cents * tax_rate / 100) if tax_rate > 0 else 0
    invoice.total_cents = invoice.subtotal_cents + invoice.tax_cents
    invoice.notes = (invoice.notes or "") + f"\nAmount overridden by {current_user.email}: {req.reason}"

    # Update line items
    sub_item = db.query(InvoiceLineItem).filter(
        InvoiceLineItem.invoice_id == invoice_id,
        InvoiceLineItem.item_type == LineItemType.SUBSCRIPTION,
    ).first()
    if sub_item:
        sub_item.unit_price_cents = req.new_amount_cents
        sub_item.total_cents = req.new_amount_cents

    tax_item = db.query(InvoiceLineItem).filter(
        InvoiceLineItem.invoice_id == invoice_id,
        InvoiceLineItem.item_type == LineItemType.TAX,
    ).first()
    if tax_item:
        tax_item.unit_price_cents = invoice.tax_cents
        tax_item.total_cents = invoice.tax_cents

    # Regenerate PDF
    try:
        from app.services.billing.pdf_generator import generate_invoice_pdf
        line_items = db.query(InvoiceLineItem).filter(InvoiceLineItem.invoice_id == invoice_id).all()
        invoice.pdf_path = generate_invoice_pdf(invoice, line_items, tenant)
    except Exception as e:
        logger.warning("PDF regeneration failed after override", error=str(e))

    try:
        db.add(AuditLog(
            tenant_id=invoice.tenant_id,
            entity_type="invoice",
            entity_id=invoice.invoice_id,
            action="invoice_amount_overridden",
            changed_by=current_user.email,
            notes=f"Amount changed from {old_total} to {invoice.total_cents}. Reason: {req.reason}",
        ))
    except Exception as e_audit:
        logger.warning("Audit log failed for invoice_amount_overridden", error=str(e_audit))

    db.commit()
    return {"message": "Amount overridden", "invoice": _invoice_to_dict(invoice)}


@router.delete("/invoices/{invoice_id}")
def soft_delete_invoice(
    invoice_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_role([UserRole.SUPER_ADMIN])),
):
    """Soft delete an invoice (sets is_archived=True)."""
    from app.db.models.invoice import Invoice
    from app.db.models.audit_log import AuditLog

    invoice = db.query(Invoice).filter(
        Invoice.invoice_id == invoice_id,
        Invoice.is_archived == False,
    ).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    invoice.is_archived = True

    try:
        db.add(AuditLog(
            tenant_id=invoice.tenant_id,
            entity_type="invoice",
            entity_id=invoice.invoice_id,
            action="invoice_deleted",
            changed_by=current_user.email,
            notes=f"Invoice {invoice.invoice_number} soft-deleted",
        ))
    except Exception as e_audit:
        logger.warning("Audit log failed for invoice_deleted", error=str(e_audit))

    db.commit()
    return {"message": f"Invoice {invoice.invoice_number} deleted"}


@router.get("/payments")
def list_payments(
    tenant_id_filter: Optional[int] = Query(None, alias="tenant_id"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user=Depends(require_role([UserRole.SUPER_ADMIN])),
):
    """List all payment records (super admin only)."""
    from app.db.models.invoice import PaymentRecord

    query = db.query(PaymentRecord).filter(PaymentRecord.is_archived == False)
    if tenant_id_filter:
        query = query.filter(PaymentRecord.tenant_id == tenant_id_filter)

    query = query.order_by(PaymentRecord.created_at.desc())
    result = paginate(query, page, page_size)

    return {
        "payments": [_payment_to_dict(p) for p in result["items"]],
        "total": result["total"],
        "page": result["page"],
        "page_size": result["page_size"],
        "pages": result["pages"],
    }


@router.get("/stats")
def billing_stats(
    db: Session = Depends(get_db),
    current_user=Depends(require_role([UserRole.SUPER_ADMIN])),
):
    """Billing statistics: outstanding, collected, overdue, MRR."""
    from sqlalchemy import func
    from app.db.models.invoice import Invoice, InvoiceStatus, PaymentRecord, PaymentStatus
    from app.db.models.tenant import Tenant

    # Total outstanding (sent + overdue)
    outstanding = db.query(func.coalesce(func.sum(Invoice.total_cents), 0)).filter(
        Invoice.status.in_([InvoiceStatus.SENT, InvoiceStatus.OVERDUE]),
        Invoice.is_archived == False,
    ).scalar()

    # Collected this month
    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    collected = db.query(func.coalesce(func.sum(PaymentRecord.amount_cents), 0)).filter(
        PaymentRecord.status == PaymentStatus.SUCCEEDED,
        PaymentRecord.created_at >= month_start,
        PaymentRecord.is_archived == False,
    ).scalar()

    # Overdue count
    overdue_count = db.query(func.count(Invoice.invoice_id)).filter(
        Invoice.status == InvoiceStatus.OVERDUE,
        Invoice.is_archived == False,
    ).scalar()

    # MRR (sum of monthly_price_cents for active tenants)
    mrr = db.query(func.coalesce(func.sum(Tenant.monthly_price_cents), 0)).filter(
        Tenant.is_active == True,
        Tenant.monthly_price_cents > 0,
    ).scalar()

    return {
        "total_outstanding_cents": outstanding,
        "collected_this_month_cents": collected,
        "overdue_count": overdue_count,
        "mrr_cents": mrr,
    }


# ─── Tenant Routes ───────────────────────────────────────────────────────────

@router.get("/my-invoices")
def my_invoices(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user=Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR])),
    tenant_id: int = Depends(get_current_tenant_id),
):
    """List own tenant's invoices."""
    from app.db.models.invoice import Invoice

    if tenant_id is None:
        raise HTTPException(status_code=400, detail="Tenant context required")

    query = db.query(Invoice).filter(
        Invoice.tenant_id == tenant_id,
        Invoice.is_archived == False,
    ).order_by(Invoice.created_at.desc())

    result = paginate(query, page, page_size)
    return {
        "invoices": [_invoice_to_dict(i) for i in result["items"]],
        "total": result["total"],
        "page": result["page"],
        "page_size": result["page_size"],
        "pages": result["pages"],
    }


@router.get("/my-invoices/{invoice_id}")
def my_invoice_detail(
    invoice_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR])),
    tenant_id: int = Depends(get_current_tenant_id),
):
    """Get invoice detail with line items (own tenant only)."""
    from app.db.models.invoice import Invoice, InvoiceLineItem

    if tenant_id is None:
        raise HTTPException(status_code=400, detail="Tenant context required")

    invoice = db.query(Invoice).filter(
        Invoice.invoice_id == invoice_id,
        Invoice.tenant_id == tenant_id,
        Invoice.is_archived == False,
    ).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    line_items = db.query(InvoiceLineItem).filter(
        InvoiceLineItem.invoice_id == invoice_id,
    ).all()

    inv_dict = _invoice_to_dict(invoice)
    inv_dict["line_items"] = [_line_item_to_dict(li) for li in line_items]
    return inv_dict


@router.get("/my-invoices/{invoice_id}/pdf")
def my_invoice_pdf(
    invoice_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR])),
    tenant_id: int = Depends(get_current_tenant_id),
):
    """Download own invoice PDF."""
    from app.db.models.invoice import Invoice

    if tenant_id is None:
        raise HTTPException(status_code=400, detail="Tenant context required")

    invoice = db.query(Invoice).filter(
        Invoice.invoice_id == invoice_id,
        Invoice.tenant_id == tenant_id,
        Invoice.is_archived == False,
    ).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    filepath = _get_pdf_filepath(invoice)
    if not filepath:
        raise HTTPException(status_code=404, detail="PDF not available")

    return FileResponse(filepath, media_type="application/pdf", filename=f"{invoice.invoice_number}.pdf")


@router.post("/my-invoices/{invoice_id}/pay")
@limiter.limit("10/hour")
def initiate_payment(
    request: Request,
    invoice_id: int,
    req: PayRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_role([UserRole.ADMIN])),
    tenant_id: int = Depends(get_current_tenant_id),
):
    """Initiate Stripe checkout for an invoice."""
    from app.db.models.invoice import Invoice, InvoiceStatus
    from app.core.config import settings

    if tenant_id is None:
        raise HTTPException(status_code=400, detail="Tenant context required")

    if not settings.STRIPE_SECRET_KEY:
        raise HTTPException(status_code=400, detail="Online payments are not configured")

    invoice = db.query(Invoice).filter(
        Invoice.invoice_id == invoice_id,
        Invoice.tenant_id == tenant_id,
        Invoice.is_archived == False,
    ).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if invoice.status == InvoiceStatus.PAID:
        raise HTTPException(status_code=400, detail="Invoice is already paid")

    from app.services.billing.payment_gateway import get_payment_gateway
    gateway = get_payment_gateway()

    base_url = settings.EFFECTIVE_BASE_URL
    success_url = req.success_url or f"{base_url}/dashboard/billing?paid={invoice.invoice_number}"
    cancel_url = req.cancel_url or f"{base_url}/dashboard/billing"

    result = gateway.create_checkout_session(
        invoice_id=invoice.invoice_id,
        amount_cents=invoice.total_cents,
        currency=invoice.currency,
        customer_email=current_user.email,
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={"tenant_id": str(tenant_id), "invoice_number": invoice.invoice_number},
    )
    return result


@router.get("/my-payments")
def my_payments(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user=Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR])),
    tenant_id: int = Depends(get_current_tenant_id),
):
    """List own tenant's payment history."""
    from app.db.models.invoice import PaymentRecord

    if tenant_id is None:
        raise HTTPException(status_code=400, detail="Tenant context required")

    query = db.query(PaymentRecord).filter(
        PaymentRecord.tenant_id == tenant_id,
        PaymentRecord.is_archived == False,
    ).order_by(PaymentRecord.created_at.desc())

    result = paginate(query, page, page_size)
    return {
        "payments": [_payment_to_dict(p) for p in result["items"]],
        "total": result["total"],
        "page": result["page"],
        "page_size": result["page_size"],
        "pages": result["pages"],
    }


# ─── Shared PDF Route ────────────────────────────────────────────────────────

@router.get("/invoices/{invoice_id}/pdf")
def download_invoice_pdf(
    invoice_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
    tenant_id: int = Depends(get_current_tenant_id),
):
    """Download invoice PDF (super admin: any; admin: own tenant)."""
    from app.db.models.invoice import Invoice

    query = db.query(Invoice).filter(
        Invoice.invoice_id == invoice_id,
        Invoice.is_archived == False,
    )

    # Non-super-admin can only see own tenant
    if current_user.role != UserRole.SUPER_ADMIN:
        if tenant_id is None:
            raise HTTPException(status_code=400, detail="Tenant context required")
        query = query.filter(Invoice.tenant_id == tenant_id)

    invoice = query.first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    filepath = _get_pdf_filepath(invoice)
    if not filepath:
        raise HTTPException(status_code=404, detail="PDF not available")

    return FileResponse(filepath, media_type="application/pdf", filename=f"{invoice.invoice_number}.pdf")


# ─── Stripe Webhook ──────────────────────────────────────────────────────────

@router.post("/webhook/stripe")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    """Stripe webhook: handles checkout.session.completed events."""
    from app.core.config import settings

    if not settings.STRIPE_SECRET_KEY or not settings.STRIPE_WEBHOOK_SECRET:
        raise HTTPException(status_code=400, detail="Stripe not configured")

    import stripe
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        invoice_id = session.get("metadata", {}).get("invoice_id")
        if not invoice_id:
            logger.warning("Stripe webhook: no invoice_id in metadata")
            return {"received": True}

        from app.db.models.invoice import Invoice, InvoiceStatus, PaymentRecord, PaymentMethod, PaymentStatus
        from app.db.models.tenant import Tenant
        from app.db.models.audit_log import AuditLog

        invoice = db.query(Invoice).filter(Invoice.invoice_id == int(invoice_id)).first()
        if not invoice:
            logger.warning("Stripe webhook: invoice not found", invoice_id=invoice_id)
            return {"received": True}

        if invoice.status == InvoiceStatus.PAID:
            return {"received": True}

        # Create payment record
        payment = PaymentRecord(
            tenant_id=invoice.tenant_id,
            invoice_id=invoice.invoice_id,
            amount_cents=session.get("amount_total", invoice.total_cents),
            currency=invoice.currency,
            payment_method=PaymentMethod.STRIPE,
            stripe_payment_id=session.get("payment_intent", ""),
            status=PaymentStatus.SUCCEEDED,
            recorded_by="stripe_webhook",
        )
        db.add(payment)

        # Update invoice
        invoice.status = InvoiceStatus.PAID
        invoice.paid_at = datetime.utcnow()
        invoice.paid_via = PaymentMethod.STRIPE
        invoice.stripe_payment_intent_id = session.get("payment_intent", "")
        invoice.payment_reference = session.get("id", "")

        try:
            db.add(AuditLog(
                tenant_id=invoice.tenant_id,
                entity_type="invoice",
                entity_id=invoice.invoice_id,
                action="invoice_paid",
                changed_by="stripe_webhook",
                notes=f"Paid via Stripe. Session: {session.get('id', '')}",
            ))
        except Exception as e_audit:
            logger.warning("Audit log failed for stripe invoice_paid", error=str(e_audit))

        db.commit()

        # Send acknowledgement email
        try:
            tenant = db.query(Tenant).filter(Tenant.tenant_id == invoice.tenant_id).first()
            if tenant:
                from app.services.billing.billing_mailer import send_payment_acknowledgement_email
                send_payment_acknowledgement_email(invoice, tenant, payment)
        except Exception as e:
            logger.warning("Post-payment email failed", error=str(e))

        logger.info("Stripe payment processed", invoice_number=invoice.invoice_number,
                    amount=session.get("amount_total"))

    return {"received": True}
