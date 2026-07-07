"""Billing & Invoicing models."""
from enum import Enum as PyEnum
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, ForeignKey, Enum, Date,
)
from app.db.base import Base


class InvoiceStatus(str, PyEnum):
    DRAFT = "draft"
    SENT = "sent"
    PAID = "paid"
    OVERDUE = "overdue"
    CANCELLED = "cancelled"
    VOID = "void"


class PaymentMethod(str, PyEnum):
    STRIPE = "stripe"
    MANUAL = "manual"
    BANK_TRANSFER = "bank_transfer"
    CHECK = "check"
    CARD = "card"


class LineItemType(str, PyEnum):
    SUBSCRIPTION = "subscription"
    ADDON = "addon"
    CREDIT = "credit"
    TAX = "tax"
    DISCOUNT = "discount"


class PaymentStatus(str, PyEnum):
    SUCCEEDED = "succeeded"
    PENDING = "pending"
    FAILED = "failed"
    REFUNDED = "refunded"


class Invoice(Base):
    """Monthly invoice for a tenant."""

    __tablename__ = "invoices"

    invoice_id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    invoice_number = Column(String(20), nullable=False, unique=True, index=True)
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)
    due_date = Column(Date, nullable=False, index=True)
    subtotal_cents = Column(Integer, nullable=False, default=0)
    tax_cents = Column(Integer, nullable=False, default=0)
    total_cents = Column(Integer, nullable=False, default=0)
    currency = Column(String(3), nullable=False, default="USD")
    status = Column(
        Enum(InvoiceStatus, values_callable=lambda x: [e.value for e in x]),
        default=InvoiceStatus.DRAFT,
        nullable=False,
        index=True,
    )
    paid_at = Column(DateTime, nullable=True)
    paid_via = Column(
        Enum(PaymentMethod, values_callable=lambda x: [e.value for e in x]),
        nullable=True,
    )
    payment_reference = Column(String(255), nullable=True)
    stripe_invoice_id = Column(String(100), nullable=True, index=True)
    stripe_payment_intent_id = Column(String(100), nullable=True)
    notes = Column(Text, nullable=True)
    pdf_path = Column(String(500), nullable=True)
    reminder_count = Column(Integer, nullable=False, default=0)
    last_reminder_at = Column(DateTime, nullable=True)


class InvoiceLineItem(Base):
    """Line item within an invoice."""

    __tablename__ = "invoice_line_items"

    line_id = Column(Integer, primary_key=True, autoincrement=True)
    invoice_id = Column(Integer, ForeignKey("invoices.invoice_id", ondelete="CASCADE"), nullable=False, index=True)
    description = Column(String(500), nullable=False)
    quantity = Column(Integer, nullable=False, default=1)
    unit_price_cents = Column(Integer, nullable=False, default=0)
    total_cents = Column(Integer, nullable=False, default=0)
    item_type = Column(
        Enum(LineItemType, values_callable=lambda x: [e.value for e in x]),
        default=LineItemType.SUBSCRIPTION,
        nullable=False,
    )


class PaymentRecord(Base):
    """Record of a payment (partial or full) against an invoice."""

    __tablename__ = "payment_records"

    payment_id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.invoice_id"), nullable=True, index=True)
    amount_cents = Column(Integer, nullable=False)
    currency = Column(String(3), nullable=False, default="USD")
    payment_method = Column(
        Enum(PaymentMethod, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    reference = Column(String(255), nullable=True)
    stripe_payment_id = Column(String(100), nullable=True, index=True)
    status = Column(
        Enum(PaymentStatus, values_callable=lambda x: [e.value for e in x]),
        default=PaymentStatus.SUCCEEDED,
        nullable=False,
        index=True,
    )
    recorded_by = Column(String(255), nullable=True)
    notes = Column(Text, nullable=True)
