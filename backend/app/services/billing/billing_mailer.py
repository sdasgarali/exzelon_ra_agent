"""Billing email sender — invoice notifications, reminders, and payment acknowledgements."""
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from pathlib import Path
import structlog

from app.core.config import settings

logger = structlog.get_logger()

_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent.parent


def _get_billing_email(tenant) -> str:
    """Get the best email address for billing communications."""
    if tenant.billing_email:
        return tenant.billing_email
    # Fallback: find tenant's admin user email
    try:
        from app.db.base import SessionLocal
        from app.db.models.user import User, UserRole
        db = SessionLocal()
        try:
            admin = db.query(User).filter(
                User.tenant_id == tenant.tenant_id,
                User.role.in_([UserRole.ADMIN, UserRole.SUPER_ADMIN]),
                User.is_active == True,
            ).first()
            if admin:
                return admin.email
        finally:
            db.close()
    except Exception:
        pass
    return None


def _send_billing_email(to_email: str, subject: str, html_body: str, pdf_path: str = None) -> bool:
    """Send a billing email with optional PDF attachment."""
    if not to_email:
        logger.warning("No billing email address available")
        return False

    if not settings.SMTP_HOST or not settings.SMTP_USER:
        logger.warning("SMTP not configured — billing email skipped", to=to_email, subject=subject)
        return False

    try:
        msg = MIMEMultipart("mixed")
        msg["From"] = settings.SMTP_USER
        msg["To"] = to_email
        msg["Subject"] = subject

        # HTML body
        msg.attach(MIMEText(html_body, "html"))

        # PDF attachment
        if pdf_path:
            abs_path = _BACKEND_DIR / pdf_path if not os.path.isabs(pdf_path) else Path(pdf_path)
            if abs_path.exists():
                with open(abs_path, "rb") as f:
                    pdf_attach = MIMEApplication(f.read(), _subtype="pdf")
                    pdf_attach.add_header(
                        "Content-Disposition", "attachment",
                        filename=abs_path.name,
                    )
                    msg.attach(pdf_attach)

        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail(settings.SMTP_USER, to_email, msg.as_string())

        logger.info("Billing email sent", to=to_email, subject=subject)
        return True

    except Exception as e:
        logger.error("Billing email failed", to=to_email, subject=subject, error=str(e))
        return False


def _format_cents(cents: int) -> str:
    return f"${cents / 100:,.2f}"


def _invoice_email_template(invoice, tenant, title: str, message: str, cta_text: str = None, cta_url: str = None) -> str:
    """Shared HTML template for all billing emails."""
    period_label = invoice.period_start.strftime("%B %Y") if invoice.period_start else "N/A"
    due_str = invoice.due_date.strftime("%B %d, %Y") if invoice.due_date else "N/A"
    company = settings.BILLING_COMPANY_NAME or settings.APP_NAME

    cta_html = ""
    if cta_text and cta_url:
        cta_html = f'''
        <div style="text-align:center;margin:24px 0;">
            <a href="{cta_url}" style="background:#2563eb;color:white;padding:12px 32px;
               border-radius:6px;text-decoration:none;font-weight:600;font-size:15px;
               display:inline-block;">{cta_text}</a>
        </div>'''

    return f'''<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#f8fafc;font-family:Arial,Helvetica,sans-serif;">
<div style="max-width:600px;margin:0 auto;padding:32px 16px;">
  <div style="background:white;border-radius:12px;padding:32px;box-shadow:0 1px 3px rgba(0,0,0,0.1);">
    <h2 style="color:#1e293b;margin:0 0 8px;">{company}</h2>
    <hr style="border:none;border-top:1px solid #e2e8f0;margin:16px 0;">

    <h3 style="color:#1e293b;margin:0 0 16px;">{title}</h3>
    <p style="color:#475569;line-height:1.6;margin:0 0 16px;">{message}</p>

    <div style="background:#f8fafc;border-radius:8px;padding:16px;margin:16px 0;">
      <table style="width:100%;border-collapse:collapse;">
        <tr><td style="color:#64748b;padding:4px 0;">Invoice Number</td>
            <td style="color:#1e293b;font-weight:600;text-align:right;padding:4px 0;">#{invoice.invoice_number}</td></tr>
        <tr><td style="color:#64748b;padding:4px 0;">Period</td>
            <td style="color:#1e293b;text-align:right;padding:4px 0;">{period_label}</td></tr>
        <tr><td style="color:#64748b;padding:4px 0;">Amount</td>
            <td style="color:#1e293b;font-weight:700;text-align:right;padding:4px 0;">{_format_cents(invoice.total_cents)}</td></tr>
        <tr><td style="color:#64748b;padding:4px 0;">Due Date</td>
            <td style="color:#1e293b;text-align:right;padding:4px 0;">{due_str}</td></tr>
      </table>
    </div>

    {cta_html}

    <hr style="border:none;border-top:1px solid #e2e8f0;margin:24px 0 16px;">
    <p style="color:#94a3b8;font-size:12px;margin:0;text-align:center;">
      {company}{' | ' + settings.BILLING_COMPANY_EMAIL if settings.BILLING_COMPANY_EMAIL else ''}
    </p>
  </div>
</div>
</body>
</html>'''


def send_new_invoice_email(invoice, tenant) -> bool:
    """Send new invoice notification with PDF attached."""
    to_email = _get_billing_email(tenant)
    period_label = invoice.period_start.strftime("%B %Y") if invoice.period_start else ""
    subject = f"Your invoice #{invoice.invoice_number} for {period_label} is ready"

    html = _invoice_email_template(
        invoice, tenant,
        title="New Invoice",
        message=f"Your invoice for {period_label} has been generated and is attached to this email.",
        cta_text="View Invoice",
        cta_url=f"{settings.EFFECTIVE_BASE_URL}/dashboard/billing",
    )
    return _send_billing_email(to_email, subject, html, pdf_path=invoice.pdf_path)


def send_reminder_email(invoice, tenant, days_overdue: int) -> bool:
    """Send overdue payment reminder."""
    to_email = _get_billing_email(tenant)
    subject = f"Reminder: Invoice #{invoice.invoice_number} is past due ({days_overdue} days overdue)"

    html = _invoice_email_template(
        invoice, tenant,
        title="Payment Reminder",
        message=(
            f"This is a friendly reminder that your invoice #{invoice.invoice_number} "
            f"is now <strong>{days_overdue} days past due</strong>. "
            f"Please arrange payment at your earliest convenience."
        ),
        cta_text="Pay Now",
        cta_url=f"{settings.EFFECTIVE_BASE_URL}/dashboard/billing",
    )
    return _send_billing_email(to_email, subject, html, pdf_path=invoice.pdf_path)


def send_payment_acknowledgement_email(invoice, tenant, payment=None) -> bool:
    """Send payment received acknowledgement."""
    to_email = _get_billing_email(tenant)
    period_label = invoice.period_start.strftime("%B %Y") if invoice.period_start else ""
    subject = f"Payment received — Thank you! Invoice #{invoice.invoice_number} is now paid"

    payment_info = ""
    if payment:
        method_val = payment.payment_method.value if hasattr(payment.payment_method, 'value') else str(payment.payment_method)
        payment_info = f" Payment method: {method_val.replace('_', ' ').title()}."

    html = _invoice_email_template(
        invoice, tenant,
        title="Payment Received",
        message=(
            f"We've received your payment for invoice #{invoice.invoice_number} "
            f"({period_label}). Thank you!{payment_info}"
        ),
        cta_text="View Receipt",
        cta_url=f"{settings.EFFECTIVE_BASE_URL}/dashboard/billing",
    )
    return _send_billing_email(to_email, subject, html)
