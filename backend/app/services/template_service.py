"""Email template business logic service."""
import html
from sqlalchemy.orm import Session
from app.db.models.email_template import EmailTemplate, TemplateStatus
from app.core.tenant_context import set_current_tenant_id, get_current_tenant_id
from app.db.query_helpers import tenant_query


def preview_template(db: Session, template_id: int) -> dict | None:
    """Generate a template preview with sample data.

    Returns None if template not found.
    """
    template = tenant_query(db, EmailTemplate).filter(
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
        "{{signature}}": "<div style='margin-top:20px;'><strong>Sarah Smith</strong><br>Exzelon Inc.</div>",
        "{{logo_url}}": "https://www.exzelon.com/gallery/logo.png",
    }

    preview_subject = template.subject
    preview_html = template.body_html
    preview_text = template.body_text or ""

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
        "placeholders_used": list(sample_data.keys()),
    }


def duplicate_template(db: Session, template_id: int) -> EmailTemplate | None:
    """Duplicate a template. Returns new template or None if not found."""
    template = tenant_query(db, EmailTemplate).filter(
        EmailTemplate.template_id == template_id
    ).first()
    if not template:
        return None

    new_template = EmailTemplate(
        name=f"{template.name} (Copy)",
        subject=template.subject,
        body_html=template.body_html,
        body_text=template.body_text,
        status=TemplateStatus.INACTIVE,
        is_default=False,
        description=template.description,
    )
    db.add(new_template)
    db.flush()
    return new_template
