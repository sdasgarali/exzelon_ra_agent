"""Email template management endpoints."""
import html
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_role, get_current_tenant_id
from app.db.models.user import User, UserRole
from app.db.models.email_template import EmailTemplate, TemplateStatus
from app.db.query_helpers import tenant_filter
from app.schemas.email_template import (
    EmailTemplateCreate,
    EmailTemplateUpdate,
    EmailTemplateResponse,
    EmailTemplateListResponse,
)

router = APIRouter(prefix="/templates", tags=["Email Templates"])


@router.get("", response_model=EmailTemplateListResponse)
async def list_templates(
    show_archived: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """List all email templates."""
    query = db.query(EmailTemplate)
    query = tenant_filter(query, EmailTemplate, tenant_id)
    if show_archived:
        query = query.filter(EmailTemplate.is_archived == True)
    else:
        query = query.filter(EmailTemplate.is_archived == False)
    templates = query.order_by(EmailTemplate.created_at.desc()).all()
    active = next((t for t in templates if t.status == TemplateStatus.ACTIVE), None)
    return EmailTemplateListResponse(
        items=[EmailTemplateResponse.model_validate(t) for t in templates],
        total=len(templates),
        active_template_id=active.template_id if active else None,
    )


@router.get("/active", response_model=Optional[EmailTemplateResponse])
async def get_active_template(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Get the currently active email template."""
    query = db.query(EmailTemplate)
    query = tenant_filter(query, EmailTemplate, tenant_id)
    template = query.filter(EmailTemplate.status == TemplateStatus.ACTIVE).first()
    if not template:
        return None
    return EmailTemplateResponse.model_validate(template)


@router.get("/{template_id}", response_model=EmailTemplateResponse)
async def get_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Get a single email template by ID."""
    template = db.query(EmailTemplate).filter(
        EmailTemplate.template_id == template_id
    ).first()
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found",
        )
    # Verify tenant ownership
    if tenant_id is not None and template.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found",
        )
    return EmailTemplateResponse.model_validate(template)


@router.post("", response_model=EmailTemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_template(
    template_in: EmailTemplateCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Create a new email template."""
    # If creating as active, deactivate all others in the same tenant
    if template_in.status == TemplateStatus.ACTIVE:
        query = db.query(EmailTemplate).filter(
            EmailTemplate.status == TemplateStatus.ACTIVE
        )
        query = tenant_filter(query, EmailTemplate, tenant_id)
        query.update({"status": TemplateStatus.INACTIVE})

    template = EmailTemplate(**template_in.model_dump())
    template.tenant_id = tenant_id or 1
    db.add(template)
    db.commit()
    db.refresh(template)
    return EmailTemplateResponse.model_validate(template)


@router.put("/{template_id}", response_model=EmailTemplateResponse)
async def update_template(
    template_id: int,
    template_in: EmailTemplateUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Update an email template."""
    template = db.query(EmailTemplate).filter(
        EmailTemplate.template_id == template_id
    ).first()
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found",
        )

    # Verify tenant ownership
    if tenant_id is not None and template.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found",
        )

    update_data = template_in.model_dump(exclude_unset=True)

    # If setting to active, deactivate all others in the same tenant
    if update_data.get("status") == TemplateStatus.ACTIVE:
        query = db.query(EmailTemplate).filter(
            EmailTemplate.status == TemplateStatus.ACTIVE,
            EmailTemplate.template_id != template_id,
        )
        query = tenant_filter(query, EmailTemplate, tenant_id)
        query.update({"status": TemplateStatus.INACTIVE})

    for field, value in update_data.items():
        setattr(template, field, value)

    db.commit()
    db.refresh(template)
    return EmailTemplateResponse.model_validate(template)


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Archive an email template (soft delete). Cannot archive the default template."""
    template = db.query(EmailTemplate).filter(
        EmailTemplate.template_id == template_id
    ).first()
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found",
        )

    # Verify tenant ownership
    if tenant_id is not None and template.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found",
        )

    if template.is_default:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete the default template",
        )
    # Soft delete: archive instead of hard deleting
    template.is_archived = True
    template.status = TemplateStatus.INACTIVE
    db.commit()


@router.post("/{template_id}/activate", response_model=EmailTemplateResponse)
async def activate_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Activate a template (deactivates all others)."""
    template = db.query(EmailTemplate).filter(
        EmailTemplate.template_id == template_id
    ).first()
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found",
        )

    # Verify tenant ownership
    if tenant_id is not None and template.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found",
        )

    # Deactivate all others in the same tenant
    query = db.query(EmailTemplate).filter(
        EmailTemplate.status == TemplateStatus.ACTIVE
    )
    query = tenant_filter(query, EmailTemplate, tenant_id)
    query.update({"status": TemplateStatus.INACTIVE})

    template.status = TemplateStatus.ACTIVE
    db.commit()
    db.refresh(template)
    return EmailTemplateResponse.model_validate(template)


@router.post("/{template_id}/preview")
async def preview_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Preview a template with sample data."""
    template = db.query(EmailTemplate).filter(
        EmailTemplate.template_id == template_id
    ).first()
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found",
        )

    # Verify tenant ownership
    if tenant_id is not None and template.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found",
        )

    sample_data = {
        "{{contact_first_name}}": "John",
        "{{sender_first_name}}": "Sarah",
        "{{job_title}}": "Senior Software Engineer",
        "{{job_location}}": "New York, NY",
        "{{company_name}}": "Acme Corp",
        "{{signature}}": "<div style='margin-top:20px;padding-top:12px;border-top:1px solid #ccc;font-family:Arial,sans-serif;'><strong>Sarah Smith</strong><br>Recruitment Specialist<br>Exzelon Inc.</div>",
        "{{logo_url}}": "https://www.exzelon.com/gallery/logo.png",
    }

    preview_subject = template.subject
    preview_html = template.body_html
    preview_text = template.body_text or ""

    for placeholder, value in sample_data.items():
        safe_value = html.escape(value)
        preview_subject = preview_subject.replace(placeholder, safe_value)
        preview_html = preview_html.replace(placeholder, value)  # HTML body keeps original (templates are HTML)
        preview_text = preview_text.replace(placeholder, safe_value)

    return {
        "template_id": template.template_id,
        "name": template.name,
        "subject": preview_subject,
        "body_html": preview_html,
        "body_text": preview_text,
        "placeholders_used": list(sample_data.keys()),
    }


@router.post("/{template_id}/duplicate", response_model=EmailTemplateResponse, status_code=status.HTTP_201_CREATED)
async def duplicate_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Duplicate an email template."""
    template = db.query(EmailTemplate).filter(
        EmailTemplate.template_id == template_id
    ).first()
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found",
        )

    # Verify tenant ownership
    if tenant_id is not None and template.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found",
        )

    new_template = EmailTemplate(
        name=f"{template.name} (Copy)",
        subject=template.subject,
        body_html=template.body_html,
        body_text=template.body_text,
        status=TemplateStatus.INACTIVE,
        is_default=False,
        description=template.description,
        tenant_id=tenant_id or 1,
    )
    db.add(new_template)
    db.commit()
    db.refresh(new_template)
    return EmailTemplateResponse.model_validate(new_template)
