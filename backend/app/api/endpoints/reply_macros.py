"""Reply macros CRUD endpoints — quick templates for inbox replies."""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc
from pydantic import BaseModel

from app.db.base import get_db
from app.api.deps.auth import get_current_active_user, require_role, get_current_tenant_id
from app.db.query_helpers import tenant_filter
from app.db.models.user import User, UserRole
from app.db.models.reply_macro import ReplyMacro

router = APIRouter(prefix="/reply-macros", tags=["Reply Macros"])


class MacroCreate(BaseModel):
    title: str
    body_text: str
    body_html: Optional[str] = None
    category: Optional[str] = None
    variables_json: Optional[str] = None


class MacroUpdate(BaseModel):
    title: Optional[str] = None
    body_text: Optional[str] = None
    body_html: Optional[str] = None
    category: Optional[str] = None
    variables_json: Optional[str] = None


def _macro_to_dict(m: ReplyMacro) -> dict:
    return {
        "macro_id": m.macro_id,
        "tenant_id": m.tenant_id,
        "title": m.title,
        "body_text": m.body_text,
        "body_html": m.body_html,
        "category": m.category,
        "variables_json": m.variables_json,
        "usage_count": m.usage_count,
        "created_by": m.created_by,
        "created_at": m.created_at.isoformat() if m.created_at else None,
        "updated_at": m.updated_at.isoformat() if m.updated_at else None,
    }


@router.get("")
def list_macros(
    category: Optional[str] = None,
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """List reply macros with optional category filter and search."""
    q = db.query(ReplyMacro).filter(ReplyMacro.is_archived == False)
    q = tenant_filter(q, ReplyMacro, tenant_id)

    if category:
        q = q.filter(ReplyMacro.category == category)
    if search:
        q = q.filter(
            ReplyMacro.title.ilike(f"%{search}%")
            | ReplyMacro.body_text.ilike(f"%{search}%")
        )

    total = q.count()
    items = q.order_by(desc(ReplyMacro.usage_count), desc(ReplyMacro.created_at)).offset(
        (page - 1) * page_size
    ).limit(page_size).all()

    return {
        "items": [_macro_to_dict(m) for m in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("")
def create_macro(
    body: MacroCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.OPERATOR])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Create a new reply macro."""
    macro = ReplyMacro(
        tenant_id=tenant_id or 1,
        title=body.title,
        body_text=body.body_text,
        body_html=body.body_html,
        category=body.category,
        variables_json=body.variables_json,
        created_by=current_user.user_id,
    )
    db.add(macro)
    db.commit()
    db.refresh(macro)
    return _macro_to_dict(macro)


@router.put("/{macro_id}")
def update_macro(
    macro_id: int,
    body: MacroUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.OPERATOR])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Update a reply macro."""
    q = db.query(ReplyMacro).filter(
        ReplyMacro.macro_id == macro_id,
        ReplyMacro.is_archived == False,
    )
    q = tenant_filter(q, ReplyMacro, tenant_id)
    macro = q.first()
    if not macro:
        raise HTTPException(status_code=404, detail="Macro not found")

    if body.title is not None:
        macro.title = body.title
    if body.body_text is not None:
        macro.body_text = body.body_text
    if body.body_html is not None:
        macro.body_html = body.body_html
    if body.category is not None:
        macro.category = body.category
    if body.variables_json is not None:
        macro.variables_json = body.variables_json

    db.commit()
    db.refresh(macro)
    return _macro_to_dict(macro)


@router.delete("/{macro_id}")
def delete_macro(
    macro_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.OPERATOR])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Soft-delete a reply macro."""
    q = db.query(ReplyMacro).filter(
        ReplyMacro.macro_id == macro_id,
        ReplyMacro.is_archived == False,
    )
    q = tenant_filter(q, ReplyMacro, tenant_id)
    macro = q.first()
    if not macro:
        raise HTTPException(status_code=404, detail="Macro not found")

    macro.is_archived = True
    db.commit()
    return {"ok": True, "macro_id": macro_id}


@router.post("/{macro_id}/use")
def use_macro(
    macro_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Increment the usage count when a macro is used."""
    q = db.query(ReplyMacro).filter(
        ReplyMacro.macro_id == macro_id,
        ReplyMacro.is_archived == False,
    )
    q = tenant_filter(q, ReplyMacro, tenant_id)
    macro = q.first()
    if not macro:
        raise HTTPException(status_code=404, detail="Macro not found")

    macro.usage_count = (macro.usage_count or 0) + 1
    db.commit()
    return {"ok": True, "macro_id": macro_id, "usage_count": macro.usage_count}
