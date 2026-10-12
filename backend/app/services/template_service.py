"""Email template business logic service."""
import html
import re
from typing import Optional

from sqlalchemy.orm import Session
from app.db.models.email_template import EmailTemplate, TemplateStatus

LOGO_PLACEHOLDER = "{{logo_url}}"
# An <img> whose src (or any attribute) uses the logo placeholder. Removed when the
# workspace has no logo, so no email ever shows a broken-image icon.
_LOGO_IMG_RE = re.compile(r"<img\b[^>]*\{\{logo_url\}\}[^>]*>", re.IGNORECASE)


def tenant_logo_url(db: Session, tenant_id: Optional[int]) -> str:
    """The workspace's own logo (white-label brand logo first, then profile logo).

    Empty when none is set — there is deliberately no platform/Exzelon fallback:
    a customer's emails must never carry another company's logo.
    """
    if not tenant_id:
        return ""
    try:
        from app.db.models.tenant import Tenant
        row = db.query(Tenant.brand_logo_url, Tenant.logo_url).filter(
            Tenant.tenant_id == tenant_id
        ).first()
    except Exception:
        return ""
    if not row:
        return ""
    return ((row[0] or "").strip() or (row[1] or "").strip())


def apply_logo(content: str, logo_url: str) -> str:
    """Substitute ``{{logo_url}}``; with no logo, drop any <img> that uses it."""
    if not content:
        return content
    logo_url = (logo_url or "").strip()
    if not logo_url:
        content = _LOGO_IMG_RE.sub("", content)
    return content.replace(LOGO_PLACEHOLDER, logo_url)


def preview_template(db: Session, template_id: int) -> dict | None:
    """Generate a template preview with sample data.

    Returns None if template not found.
    """
    template = db.query(EmailTemplate).filter(
        EmailTemplate.template_id == template_id
    ).first()
    if not template:
        return None

    sample_data = {
        "{{contact_first_name}}": "John",
        "{{sender_first_name}}": "Sarah",
        "{{job_title}}": "Senior Software Engineer",
        "{{job_location}}": "New York, NY",
        "{{company_name}}": "Acme Corp",
        "{{signature}}": "<div style='margin-top:20px;'><strong>Sarah Smith</strong><br>Your Company</div>",
    }
    # The workspace's own logo, or none (the <img> is dropped) — never a platform default.
    logo_url = tenant_logo_url(db, template.tenant_id)

    preview_subject = apply_logo(template.subject, html.escape(logo_url))
    preview_html = apply_logo(template.body_html, html.escape(logo_url))
    preview_text = apply_logo(template.body_text or "", logo_url)

    for placeholder, value in sample_data.items():
        safe_value = html.escape(value)
        preview_subject = preview_subject.replace(placeholder, safe_value)
        preview_html = preview_html.replace(placeholder, value)
        preview_text = preview_text.replace(placeholder, safe_value)

    return {
        "template_id": template.template_id,
        "name": template.name,
        "subject": preview_subject,
        "body_html": preview_html,
        "body_text": preview_text,
        "placeholders_used": list(sample_data.keys()) + [LOGO_PLACEHOLDER],
    }


def duplicate_template(db: Session, template_id: int) -> EmailTemplate | None:
    """Duplicate a template. Returns new template or None if not found."""
    template = db.query(EmailTemplate).filter(
        EmailTemplate.template_id == template_id
    ).first()
    if not template:
        return None

    new_template = EmailTemplate(
        tenant_id=template.tenant_id,
        name=f"{template.name} (Copy)",
        subject=template.subject,
        body_html=template.body_html,
        body_text=template.body_text,
        status=TemplateStatus.INACTIVE,
        category=template.category,
        is_default=False,
        description=template.description,
    )
    db.add(new_template)
    db.flush()
    return new_template
