"""Billing & Invoicing API endpoints."""
import json
from datetime import date, datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps.database import get_db
from app.api.deps.auth import get_current_active_user, require_role, get_current_tenant_id, require_tenant_id
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

def _clear_suspension_if_settled(db, tenant_id: int) -> None:
    """Lift a non-payment suspension once a tenant has no unpaid (sent/overdue)
    invoices left. Safe to call after any payment. (ELR-023)"""
    from app.db.models.invoice import Invoice, InvoiceStatus
    from app.db.models.tenant import Tenant
    tenant = db.query(Tenant).filter(Tenant.tenant_id == tenant_id).first()
    if tenant is None or not getattr(tenant, "billing_suspended", False):
        return
    still_unpaid = db.query(Invoice.invoice_id).filter(
        Invoice.tenant_id == tenant_id,
        Invoice.status.in_((InvoiceStatus.SENT, InvoiceStatus.OVERDUE)),
        Invoice.is_archived == False,
    ).first() is not None
    if not still_unpaid:
        tenant.billing_suspended = False


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
    _clear_suspension_if_settled(db, invoice.tenant_id)  # ELR-023

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
    # An issued (sent/paid) invoice is immutable — editing it would rewrite a
    # document the customer already has. Only drafts can be amended; a sent invoice
    # must be voided and re-issued (or credited). (ELR-030)
    if invoice.status != InvoiceStatus.DRAFT:
        raise HTTPException(
            status_code=400,
            detail="Only draft invoices can be amended. Void and re-issue an already-sent invoice.",
        )

    old_total = invoice.total_cents
    invoice.subtotal_cents = req.new_amount_cents

    # Recalculate tax
    from app.db.models.tenant import Tenant
    tenant = db.query(Tenant).filter(Tenant.tenant_id == invoice.tenant_id).first()
    tax_rate = float(tenant.tax_rate_percent or 0) if tenant else 0
    from app.services.billing.invoice_generator import compute_tax_cents
    invoice.tax_cents = compute_tax_cents(req.new_amount_cents, tax_rate)
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
    current_user=Depends(require_role([UserRole.ADMIN, UserRole.BDM])),
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
    current_user=Depends(require_role([UserRole.ADMIN, UserRole.BDM])),
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
    current_user=Depends(require_role([UserRole.ADMIN, UserRole.BDM])),
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
    current_user=Depends(require_role([UserRole.ADMIN, UserRole.BDM])),
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


# ─── Subscriptions (ELR-021) ─────────────────────────────────────────────────

class SubscribeRequest(BaseModel):
    plan: Optional[str] = None  # defaults to the tenant's current plan
    annual: bool = False        # bill yearly at the discounted per-month rate
    success_url: str = Field(default="")
    cancel_url: str = Field(default="")


@router.post("/subscription/checkout")
def subscription_checkout(
    req: SubscribeRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN])),
    tenant_id: int = Depends(require_tenant_id),
):
    """Start a recurring-subscription Checkout for the tenant's plan (ELR-021)."""
    from app.core.config import settings
    from app.core.plans import is_custom, normalize_plan
    from app.services.billing.subscription_service import price_id_for_plan
    from app.db.models.tenant import Tenant
    tenant = db.query(Tenant).filter(Tenant.tenant_id == tenant_id).first()
    plan = normalize_plan(req.plan or (tenant.plan if tenant else None))

    if plan == "free":
        raise HTTPException(status_code=400, detail="The Free plan has nothing to pay for.")
    if is_custom(plan):
        # Custom contracts are quoted and invoiced manually, never self-serve.
        raise HTTPException(
            status_code=400,
            detail="Custom plans are billed by contract. Request a quote instead.",
        )

    price_id = price_id_for_plan(plan, annual=req.annual)
    if not price_id:
        term = "annual" if req.annual else "monthly"
        raise HTTPException(
            status_code=400,
            detail=f"No Stripe {term} price configured for plan '{plan}'. Set STRIPE_PRICE_* first.",
        )
    if not settings.STRIPE_SECRET_KEY:
        raise HTTPException(status_code=400, detail="Online payments are not configured")

    from app.services.billing.payment_gateway import get_payment_gateway
    base_url = settings.EFFECTIVE_BASE_URL
    result = get_payment_gateway().create_subscription_checkout(
        price_id=price_id,
        customer_email=current_user.email,
        success_url=req.success_url or f"{base_url}/dashboard/billing?subscribed=1",
        cancel_url=req.cancel_url or f"{base_url}/dashboard/billing",
        metadata={
            "tenant_id": str(tenant_id),
            "plan": plan or "",
            "term": "annual" if req.annual else "monthly",
        },
    )
    return result


@router.get("/usage")
def plan_usage(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Everything the usage screen and the upgrade prompt need, in one call.

    Deliberately one endpoint rather than four: the billing page wants credits, sends,
    resource counts and the plan's own numbers on screen together, and four round-trips
    would let them disagree with each other mid-render.

    `near_limit` is computed here rather than in the UI so "when do we nudge someone to
    upgrade?" is one rule in one place instead of a threshold copy-pasted into every
    meter component.
    """
    from app.api.deps.plan_limits import RESOURCE_COUNTERS, RESOURCE_LIMITS
    from app.core.plans import (
        PLAN_MATRIX, get_plan, is_custom, limits_for_tenant, normalize_plan,
        plan_features,
    )
    from app.db.models.tenant import Tenant
    from app.services.credit_metering import available_credits, get_usage_summary
    from app.services.send_quota import quota_status

    if tenant_id is None:
        return {"metered": False, "message": "Super admin usage is not metered."}

    tenant = db.query(Tenant).filter(Tenant.tenant_id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    plan_key = normalize_plan(tenant.plan)
    spec = get_plan(plan_key)
    credits = available_credits(db, tenant_id)
    sends = quota_status(db, tenant_id)
    limits = limits_for_tenant(tenant)

    # Resource meters, using the same counters the 403 gate enforces — so what the
    # screen shows and what blocks a create can never drift apart.
    resources = []
    for key, limit_field in RESOURCE_LIMITS.items():
        limit = limits.get(limit_field, 0)
        used = RESOURCE_COUNTERS[key](db, tenant_id)
        resources.append({
            "resource": key,
            "used": used,
            "limit": limit,
            "remaining": max(0, limit - used),
            "percent": round(used / limit * 100, 1) if limit > 0 else None,
            "near_limit": limit > 0 and used / limit >= 0.8,
        })

    credit_pct = (
        round((credits["period_spent"] or 0) / credits["plan_allowance"] * 100, 1)
        if credits.get("plan_allowance") else None
    )
    next_plan = {"free": "pro", "pro": "max"}.get(plan_key)

    return {
        "metered": True,
        "plan": {
            "key": plan_key,
            "label": spec.label,
            "is_custom": is_custom(plan_key),
            "monthly_price_cents": None if is_custom(plan_key) else spec.monthly_price_cents,
            "annual_price_cents": None if is_custom(plan_key) else spec.annual_price_cents,
            "upgrade_to": next_plan,
            "upgrade_label": PLAN_MATRIX[next_plan].label if next_plan else None,
        },
        # What this plan includes. The UI uses it to hide nav for features the tenant
        # cannot reach and — more importantly — to stop polling gated endpoints, which
        # otherwise 402 on every page load and fill the console with errors that look
        # like bugs. It is presentation only: the server-side gate is the enforcement.
        "features": sorted(plan_features(plan_key)),
        "credits": {
            **credits,
            "percent": credit_pct,
            "near_limit": credit_pct is not None and credit_pct >= 80,
        },
        "sends": {
            **sends,
            "percent": round(sends["used"] / sends["limit"] * 100, 1) if sends.get("limit") else None,
            "near_limit": bool(sends.get("limit")) and sends["used"] / sends["limit"] >= 0.8,
        },
        "resources": resources,
        "breakdown": get_usage_summary(db, tenant_id, days=30).get("usage", []),
    }


class CreditTopupRequest(BaseModel):
    """Buy credits in blocks. Default block: 1,000 credits for $10."""
    blocks: int = Field(default=1, ge=1, le=500)
    success_url: str = Field(default="")
    cancel_url: str = Field(default="")


@router.post("/credits/topup")
def buy_credit_topup(
    req: CreditTopupRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN])),
    tenant_id: int = Depends(require_tenant_id),
):
    """Start Checkout for a credit top-up.

    Top-ups are priced at the same rate as the plan allowance ($0.01/credit) — running
    out mid-month shouldn't cost more per credit than planning ahead did. They never
    expire and are only drawn on once the monthly allowance is spent.

    Credits are granted by the `checkout.session.completed` webhook, never here, so a
    user who abandons Checkout is not credited.
    """
    from app.core.config import settings
    from app.core.plans import normalize_plan

    plan = normalize_plan(getattr(_tenant_or_404(db, tenant_id), "plan", None))
    if plan == "free":
        raise HTTPException(
            status_code=400,
            detail="Top-ups are available on paid plans. Upgrade to Pro to buy credits.",
        )

    price_id = settings.STRIPE_PRICE_CREDIT_TOPUP
    if not price_id:
        raise HTTPException(
            status_code=400,
            detail="No Stripe price configured for credit top-ups. Set STRIPE_PRICE_CREDIT_TOPUP.",
        )
    if not settings.STRIPE_SECRET_KEY:
        raise HTTPException(status_code=400, detail="Online payments are not configured")

    credits = req.blocks * settings.CREDIT_TOPUP_BLOCK_SIZE
    base_url = settings.EFFECTIVE_BASE_URL
    from app.services.billing.payment_gateway import get_payment_gateway
    result = get_payment_gateway().create_one_time_checkout(
        price_id=price_id,
        customer_email=current_user.email,
        success_url=req.success_url or f"{base_url}/dashboard/billing?topup=1",
        cancel_url=req.cancel_url or f"{base_url}/dashboard/billing",
        quantity=req.blocks,
        metadata={
            "tenant_id": str(tenant_id),
            "purpose": "credit_topup",
            "credits": str(credits),
        },
    )
    return {
        **result,
        "credits": credits,
        "price_cents": req.blocks * settings.CREDIT_TOPUP_BLOCK_PRICE_CENTS,
    }


def _tenant_or_404(db: Session, tenant_id: int):
    from app.db.models.tenant import Tenant
    tenant = db.query(Tenant).filter(Tenant.tenant_id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant


class CustomQuoteRequest(BaseModel):
    """A "build your own plan" request. Every axis is floored at Max's number."""
    mailboxes: Optional[int] = None
    credits_per_month: Optional[int] = None
    sends_per_month: Optional[int] = None
    campaigns: Optional[int] = None
    notes: str = Field(default="", max_length=2000)


@router.post("/custom-quote")
def request_custom_quote(
    req: CustomQuoteRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN])),
    tenant_id: int = Depends(require_tenant_id),
):
    """Record a request for a Custom plan and notify us.

    Custom sits above Max: the customer picks their own numbers and we quote against
    them, so anything at or below Max's figure is rejected with the floor it must
    clear — otherwise "custom" would be a way to negotiate *down* from the published
    tier. No payment is taken here; contracts are invoiced through the ManualGateway.
    """
    from app.core.plans import PLAN_MATRIX
    from app.services.audit_helper import write_audit_log

    max_spec = PLAN_MATRIX["max"]
    floors = {
        "mailboxes": max_spec.max_mailboxes,
        "credits_per_month": max_spec.credits_per_month,
        "sends_per_month": max_spec.send_quota_per_month,
        "campaigns": max_spec.max_campaigns,
    }

    requested = {k: getattr(req, k) for k in floors if getattr(req, k) is not None}
    if not requested:
        raise HTTPException(
            status_code=400,
            detail="Specify at least one limit above Max to request a custom quote.",
        )

    too_small = {k: floors[k] for k, v in requested.items() if int(v) <= floors[k]}
    if too_small:
        detail = ", ".join(f"{k} must exceed {v}" for k, v in sorted(too_small.items()))
        raise HTTPException(
            status_code=400,
            detail=f"A custom plan sits above Max: {detail}",
        )

    write_audit_log(
        db, tenant_id=tenant_id, entity_type="tenant", entity_id=tenant_id,
        action="custom_quote_requested", changed_by=current_user.email,
        notes=json.dumps({"requested": requested, "notes": req.notes})[:500],
    )
    db.commit()

    logger.info("custom_quote_requested", tenant_id=tenant_id,
                requested=requested, requested_by=current_user.email)

    return {
        "status": "received",
        "requested": requested,
        "floors": floors,
        "message": "Thanks — we'll be in touch with a quote.",
    }


@router.get("/subscription")
def get_subscription_status(
    db: Session = Depends(get_db),
    current_user=Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Current subscription for the tenant (or null)."""
    from app.db.models.subscription import SubscriptionRecord
    from app.db.query_helpers import tenant_filter
    rec = tenant_filter(db.query(SubscriptionRecord), SubscriptionRecord, tenant_id).first()
    if not rec:
        return {"subscription": None}
    return {"subscription": {
        "plan": rec.plan, "status": rec.status.value,
        "cancel_at_period_end": rec.cancel_at_period_end,
        "current_period_end": rec.current_period_end.isoformat() if rec.current_period_end else None,
        "stripe_subscription_id": rec.stripe_subscription_id,
    }}


@router.post("/subscription/cancel")
def cancel_subscription(
    db: Session = Depends(get_db),
    current_user=Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN])),
    tenant_id: int = Depends(require_tenant_id),
):
    """Cancel the tenant's subscription at period end (ELR-021)."""
    from app.db.models.subscription import SubscriptionRecord
    rec = db.query(SubscriptionRecord).filter(
        SubscriptionRecord.tenant_id == tenant_id).first()
    if not rec or not rec.stripe_subscription_id:
        raise HTTPException(status_code=404, detail="No active subscription")
    from app.services.billing.payment_gateway import get_payment_gateway
    get_payment_gateway().cancel_subscription(rec.stripe_subscription_id, at_period_end=True)
    rec.cancel_at_period_end = True
    db.commit()
    return {"message": "Subscription will cancel at period end", "canceled_at_period_end": True}


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

    from app.db.models.invoice import (
        Invoice, InvoiceStatus, PaymentRecord, PaymentMethod, PaymentStatus,
        ProcessedStripeEvent,
    )
    from app.db.models.tenant import Tenant
    from app.db.models.audit_log import AuditLog
    from sqlalchemy.exc import IntegrityError

    # Idempotency: Stripe delivers at-least-once and retries. If we've already
    # processed this event id, do nothing (never double-record a payment). (ELR-008)
    event_id = event.get("id")
    if event_id and db.query(ProcessedStripeEvent).filter(
        ProcessedStripeEvent.event_id == event_id
    ).first():
        return {"received": True, "duplicate": True}

    def _mark_processed_and_commit():
        """Record the event id and commit in one transaction. On a concurrent
        duplicate the UNIQUE pk raises IntegrityError → treat as already-processed."""
        if event_id:
            db.add(ProcessedStripeEvent(event_id=event_id, event_type=event.get("type")))
        try:
            db.commit()
            return True
        except IntegrityError:
            db.rollback()
            return False

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        meta = session.get("metadata", {}) or {}

        # Credit top-up → grant the credits. Done here rather than at checkout time so
        # an abandoned or failed payment never results in free credits. The
        # ProcessedStripeEvent guard above makes Stripe's at-least-once delivery safe:
        # a retried webhook must not grant the credits twice.
        if meta.get("purpose") == "credit_topup":
            tid = meta.get("tenant_id")
            credits = meta.get("credits")
            if tid and credits:
                from app.services.credit_metering import grant_topup
                grant_topup(
                    db, int(tid), float(credits),
                    reference_id=session.get("id"),
                    description=f"Top-up: {int(float(credits)):,} credits",
                    commit=False,
                )
                logger.info("credit_topup_paid", tenant_id=int(tid), credits=credits,
                            session_id=session.get("id"))
            else:
                logger.warning("Stripe webhook: credit_topup missing tenant_id/credits",
                               metadata=meta)
            _mark_processed_and_commit()
            return {"received": True}

        # Subscription checkout → link tenant↔subscription; details arrive via the
        # customer.subscription.* events. (ELR-021)
        if session.get("subscription"):
            tid = session.get("metadata", {}).get("tenant_id")
            if tid:
                from app.services.billing.subscription_service import upsert_from_stripe
                upsert_from_stripe(db, {
                    "id": session.get("subscription"),
                    "customer": session.get("customer"),
                    "status": "active",
                    "metadata": session.get("metadata", {}),
                }, int(tid))
            _mark_processed_and_commit()
            return {"received": True}

        invoice_id = session.get("metadata", {}).get("invoice_id")
        if not invoice_id:
            logger.warning("Stripe webhook: no invoice_id in metadata")
            _mark_processed_and_commit()
            return {"received": True}

        invoice = db.query(Invoice).filter(Invoice.invoice_id == int(invoice_id)).first()
        if not invoice:
            logger.warning("Stripe webhook: invoice not found", invoice_id=invoice_id)
            _mark_processed_and_commit()
            return {"received": True}

        if invoice.status == InvoiceStatus.PAID:
            _mark_processed_and_commit()
            return {"received": True}

        # Verify the payment matches the invoice before marking paid: the amount
        # Stripe charged must equal what we billed, and the metadata tenant (if
        # present) must match the invoice's tenant. A mismatch is refused (400 →
        # Stripe retries) rather than silently accepted. (ELR-008)
        amount_total = session.get("amount_total")
        if amount_total is not None and int(amount_total) != invoice.total_cents:
            logger.warning("Stripe webhook: amount mismatch",
                           invoice_id=invoice.invoice_id,
                           charged=amount_total, billed=invoice.total_cents)
            raise HTTPException(status_code=400, detail="Amount does not match invoice total")
        meta_tenant = session.get("metadata", {}).get("tenant_id")
        if meta_tenant is not None and int(meta_tenant) != invoice.tenant_id:
            logger.warning("Stripe webhook: tenant mismatch",
                           invoice_id=invoice.invoice_id,
                           meta_tenant=meta_tenant, invoice_tenant=invoice.tenant_id)
            raise HTTPException(status_code=400, detail="Tenant does not match invoice")

        payment = PaymentRecord(
            tenant_id=invoice.tenant_id,
            invoice_id=invoice.invoice_id,
            amount_cents=amount_total if amount_total is not None else invoice.total_cents,
            currency=invoice.currency,
            payment_method=PaymentMethod.STRIPE,
            stripe_payment_id=session.get("payment_intent", ""),
            status=PaymentStatus.SUCCEEDED,
            recorded_by="stripe_webhook",
        )
        db.add(payment)

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

        # Lift a non-payment suspension immediately if this clears their arrears (ELR-023).
        _clear_suspension_if_settled(db, invoice.tenant_id)

        # Record the event id in the SAME transaction as the payment/invoice update
        # so processing and de-dup are all-or-nothing.
        if not _mark_processed_and_commit():
            return {"received": True, "duplicate": True}

        # Send acknowledgement email
        try:
            tenant = db.query(Tenant).filter(Tenant.tenant_id == invoice.tenant_id).first()
            if tenant:
                from app.services.billing.billing_mailer import send_payment_acknowledgement_email
                send_payment_acknowledgement_email(invoice, tenant, payment)
        except Exception as e:
            logger.warning("Post-payment email failed", error=str(e))

        logger.info("Stripe payment processed", invoice_number=invoice.invoice_number,
                    amount=amount_total)

    elif event["type"] in ("charge.refunded", "charge.dispute.created",
                           "payment_intent.payment_failed", "invoice.payment_failed"):
        # Resolve the invoice from the payment intent (these events don't carry our
        # metadata). No match → just record the event and move on. (ELR-022)
        obj = event["data"]["object"]
        pi = obj.get("payment_intent") or obj.get("id")
        invoice = None
        if pi:
            invoice = db.query(Invoice).filter(Invoice.stripe_payment_intent_id == pi).first()

        if invoice is not None:
            etype = event["type"]
            if etype == "charge.refunded":
                invoice.status = InvoiceStatus.REFUNDED
                refunded = obj.get("amount_refunded", invoice.total_cents)
                db.add(PaymentRecord(
                    tenant_id=invoice.tenant_id, invoice_id=invoice.invoice_id,
                    amount_cents=-int(refunded), currency=invoice.currency,
                    payment_method=PaymentMethod.STRIPE,
                    stripe_payment_id=pi, status=PaymentStatus.REFUNDED,
                    recorded_by="stripe_webhook", notes="Refund via Stripe",
                ))
                action = "invoice_refunded"
            elif etype == "charge.dispute.created":
                # Don't auto-void a disputed invoice — flag it for a human.
                invoice.notes = (invoice.notes or "") + "\n[DISPUTE] Chargeback opened via Stripe."
                action = "invoice_disputed"
            else:  # payment failed
                if invoice.status != InvoiceStatus.PAID:
                    invoice.status = InvoiceStatus.OVERDUE
                action = "invoice_payment_failed"
            try:
                db.add(AuditLog(
                    tenant_id=invoice.tenant_id, entity_type="invoice",
                    entity_id=invoice.invoice_id, action=action,
                    changed_by="stripe_webhook", notes=f"Stripe event {event['type']}",
                ))
            except Exception:
                pass
            logger.info("Stripe lifecycle event processed",
                        invoice_id=invoice.invoice_id, event_type=event["type"])
        if not _mark_processed_and_commit():
            return {"received": True, "duplicate": True}

    elif event["type"].startswith("customer.subscription."):
        # Subscription lifecycle: created / updated / deleted. Keep our
        # SubscriptionRecord (and the tenant's plan) in sync. (ELR-021)
        from app.db.models.subscription import SubscriptionRecord
        sub_obj = event["data"]["object"]
        tid = (sub_obj.get("metadata") or {}).get("tenant_id")
        if not tid:
            existing = db.query(SubscriptionRecord).filter(
                SubscriptionRecord.stripe_subscription_id == sub_obj.get("id")).first()
            tid = existing.tenant_id if existing else None
        if tid:
            from app.services.billing.subscription_service import upsert_from_stripe
            upsert_from_stripe(db, sub_obj, int(tid))
        _mark_processed_and_commit()

    else:
        # Unhandled event type — record it so retries of the same id are no-ops.
        _mark_processed_and_commit()

    return {"received": True}
