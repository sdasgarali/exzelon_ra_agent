"""Objection handling template CRUD endpoints."""
import structlog
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps.database import get_db
from app.api.deps.auth import get_current_active_user, require_role, get_current_tenant_id
from app.db.query_helpers import tenant_filter
from app.db.models.user import User, UserRole
from app.db.models.objection_template import ObjectionTemplate

logger = structlog.get_logger()

router = APIRouter(prefix="/objections", tags=["objections"])


class ObjectionCreate(BaseModel):
    objection_type: str  # budget/timing/authority/need/competitor/trust/followup/custom
    objection_text: str
    response_text: str
    category: Optional[str] = None


class ObjectionUpdate(BaseModel):
    objection_type: Optional[str] = None
    objection_text: Optional[str] = None
    response_text: Optional[str] = None
    category: Optional[str] = None
    effectiveness_score: Optional[int] = None


@router.get("")
def list_objections(
    objection_type: Optional[str] = None,
    category: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """List all objection templates (tenant-filtered, category filter)."""
    q = db.query(ObjectionTemplate).filter(ObjectionTemplate.is_archived == False)
    q = tenant_filter(q, ObjectionTemplate, tenant_id)

    if objection_type:
        q = q.filter(ObjectionTemplate.objection_type == objection_type)
    if category:
        q = q.filter(ObjectionTemplate.category == category)

    total = q.count()
    templates = q.order_by(
        ObjectionTemplate.effectiveness_score.desc(),
        ObjectionTemplate.created_at.desc(),
    ).offset((page - 1) * page_size).limit(page_size).all()

    return {
        "items": [
            {
                "template_id": t.template_id,
                "objection_type": t.objection_type,
                "objection_text": t.objection_text,
                "response_text": t.response_text,
                "category": t.category,
                "effectiveness_score": t.effectiveness_score,
                "times_used": t.times_used,
                "times_approved": t.times_approved,
                "is_system": t.is_system,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in templates
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size,
    }


@router.post("")
def create_objection(
    data: ObjectionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([UserRole.ADMIN, UserRole.BDM])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Create a custom objection template."""
    template = ObjectionTemplate(
        tenant_id=tenant_id or 1,
        objection_type=data.objection_type,
        objection_text=data.objection_text,
        response_text=data.response_text,
        category=data.category,
        is_system=False,
        effectiveness_score=50,
        created_by=user.user_id,
    )
    db.add(template)
    db.commit()
    db.refresh(template)

    logger.info("objection_template_created", template_id=template.template_id, user=user.email)
    return {
        "template_id": template.template_id,
        "objection_type": template.objection_type,
        "message": "Objection template created",
    }


@router.put("/{template_id}")
def update_objection(
    template_id: int,
    data: ObjectionUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([UserRole.ADMIN, UserRole.BDM])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Update an objection template."""
    q = db.query(ObjectionTemplate).filter(
        ObjectionTemplate.template_id == template_id,
        ObjectionTemplate.is_archived == False,
    )
    q = tenant_filter(q, ObjectionTemplate, tenant_id)
    template = q.first()

    if not template:
        raise HTTPException(status_code=404, detail="Objection template not found")

    if data.objection_type is not None:
        template.objection_type = data.objection_type
    if data.objection_text is not None:
        template.objection_text = data.objection_text
    if data.response_text is not None:
        template.response_text = data.response_text
    if data.category is not None:
        template.category = data.category
    if data.effectiveness_score is not None:
        template.effectiveness_score = max(0, min(100, data.effectiveness_score))

    db.commit()
    db.refresh(template)

    return {
        "template_id": template.template_id,
        "message": "Objection template updated",
    }


@router.delete("/{template_id}")
def delete_objection(
    template_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([UserRole.ADMIN])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Soft-delete an objection template (only non-system templates)."""
    q = db.query(ObjectionTemplate).filter(
        ObjectionTemplate.template_id == template_id,
        ObjectionTemplate.is_archived == False,
    )
    q = tenant_filter(q, ObjectionTemplate, tenant_id)
    template = q.first()

    if not template:
        raise HTTPException(status_code=404, detail="Objection template not found")

    if template.is_system:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete system-provided objection templates",
        )

    template.is_archived = True
    db.commit()

    logger.info("objection_template_deleted", template_id=template_id, user=user.email)
    return {"message": "Objection template deleted", "template_id": template_id}


@router.post("/seed")
def seed_objections(
    db: Session = Depends(get_db),
    user: User = Depends(require_role([UserRole.ADMIN])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Seed system objection templates for the current tenant."""
    from app.services.objection_handler import seed_system_objections

    result = seed_system_objections(db, tenant_id=tenant_id or 1)
    return result


@router.post("/{template_id}/use")
def use_objection(
    template_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Increment usage counter and return response text."""
    q = db.query(ObjectionTemplate).filter(
        ObjectionTemplate.template_id == template_id,
        ObjectionTemplate.is_archived == False,
    )
    q = tenant_filter(q, ObjectionTemplate, tenant_id)
    template = q.first()

    if not template:
        raise HTTPException(status_code=404, detail="Objection template not found")

    template.times_used = (template.times_used or 0) + 1
    db.commit()

    return {
        "template_id": template.template_id,
        "objection_type": template.objection_type,
        "response_text": template.response_text,
        "effectiveness_score": template.effectiveness_score,
        "times_used": template.times_used,
    }
