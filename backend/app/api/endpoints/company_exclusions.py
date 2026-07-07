"""Company exclusion management endpoints."""
import os
import structlog
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.api.deps import get_db, require_role, get_current_tenant_id
from app.db.models.user import UserRole
from app.db.models.company_exclusion import CompanyExclusion, normalize_company_for_exclusion

logger = structlog.get_logger()

router = APIRouter(prefix="/company-exclusions", tags=["Company Exclusions"])


# ---------- Schemas ----------

class ExclusionCreate(BaseModel):
    company_name: str
    category: Optional[str] = None
    lob_id: Optional[int] = None
    is_active: bool = True


class ExclusionBulkCreate(BaseModel):
    companies: List[ExclusionCreate]


class ExclusionUpdate(BaseModel):
    company_name: Optional[str] = None
    category: Optional[str] = None
    is_active: Optional[bool] = None


class ExclusionToggleAll(BaseModel):
    is_active: bool
    lob_id: Optional[int] = None
    category: Optional[str] = None


class ExclusionBulkDelete(BaseModel):
    exclusion_ids: List[int]


class ExclusionResponse(BaseModel):
    exclusion_id: int
    tenant_id: int
    lob_id: Optional[int] = None
    company_name: str
    company_name_normalized: str
    category: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ---------- Endpoints ----------

@router.get("", response_model=List[ExclusionResponse])
async def list_exclusions(
    db: Session = Depends(get_db),
    current_user=Depends(require_role([UserRole.ADMIN])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
    lob_id: Optional[int] = Query(None, description="Filter by LOB"),
    category: Optional[str] = Query(None, description="Filter by category"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    search: Optional[str] = Query(None, description="Search company name"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=5000),
):
    """List excluded companies for the current tenant."""
    if tenant_id is None:
        raise HTTPException(status_code=400, detail="No tenant context")

    q = db.query(CompanyExclusion).filter(CompanyExclusion.tenant_id == tenant_id)

    if lob_id is not None:
        q = q.filter(CompanyExclusion.lob_id == lob_id)
    if category is not None:
        q = q.filter(CompanyExclusion.category == category)
    if is_active is not None:
        q = q.filter(CompanyExclusion.is_active == is_active)
    if search:
        q = q.filter(CompanyExclusion.company_name.ilike(f"%{search}%"))

    q = q.order_by(CompanyExclusion.company_name)
    return q.offset(skip).limit(limit).all()


@router.get("/count")
async def count_exclusions(
    db: Session = Depends(get_db),
    current_user=Depends(require_role([UserRole.ADMIN])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
    lob_id: Optional[int] = Query(None),
    category: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    search: Optional[str] = Query(None),
):
    """Get count of excluded companies (for pagination)."""
    if tenant_id is None:
        raise HTTPException(status_code=400, detail="No tenant context")

    q = db.query(CompanyExclusion).filter(CompanyExclusion.tenant_id == tenant_id)
    if lob_id is not None:
        q = q.filter(CompanyExclusion.lob_id == lob_id)
    if category is not None:
        q = q.filter(CompanyExclusion.category == category)
    if is_active is not None:
        q = q.filter(CompanyExclusion.is_active == is_active)
    if search:
        q = q.filter(CompanyExclusion.company_name.ilike(f"%{search}%"))

    total = q.count()
    active = q.filter(CompanyExclusion.is_active == True).count() if is_active is None else (total if is_active else 0)
    return {"total": total, "active": active}


@router.get("/categories")
async def list_categories(
    db: Session = Depends(get_db),
    current_user=Depends(require_role([UserRole.ADMIN])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """List distinct categories for the tenant's exclusions."""
    if tenant_id is None:
        raise HTTPException(status_code=400, detail="No tenant context")

    rows = (
        db.query(CompanyExclusion.category)
        .filter(CompanyExclusion.tenant_id == tenant_id, CompanyExclusion.category != None)
        .distinct()
        .all()
    )
    return [r[0] for r in rows if r[0]]


@router.post("", response_model=ExclusionResponse, status_code=201)
async def create_exclusion(
    data: ExclusionCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_role([UserRole.ADMIN])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Add a single company to the exclusion list."""
    if tenant_id is None:
        raise HTTPException(status_code=400, detail="No tenant context")

    normalized = normalize_company_for_exclusion(data.company_name)
    if not normalized:
        raise HTTPException(status_code=400, detail="Company name is empty after normalization")

    existing = db.query(CompanyExclusion).filter(
        CompanyExclusion.tenant_id == tenant_id,
        CompanyExclusion.company_name_normalized == normalized,
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Company '{data.company_name}' is already excluded")

    exclusion = CompanyExclusion(
        tenant_id=tenant_id,
        lob_id=data.lob_id,
        company_name=data.company_name.strip(),
        company_name_normalized=normalized,
        category=data.category,
        is_active=data.is_active,
    )
    db.add(exclusion)
    db.commit()
    db.refresh(exclusion)
    return exclusion


@router.post("/bulk", status_code=201)
async def bulk_create_exclusions(
    data: ExclusionBulkCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_role([UserRole.ADMIN])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Bulk-add companies to the exclusion list. Duplicates are skipped."""
    if tenant_id is None:
        raise HTTPException(status_code=400, detail="No tenant context")

    # Load existing normalized names for this tenant
    existing_normalized = set(
        r[0] for r in db.query(CompanyExclusion.company_name_normalized)
        .filter(CompanyExclusion.tenant_id == tenant_id)
        .all()
    )

    created = 0
    skipped = 0
    for item in data.companies:
        normalized = normalize_company_for_exclusion(item.company_name)
        if not normalized or normalized in existing_normalized:
            skipped += 1
            continue
        exclusion = CompanyExclusion(
            tenant_id=tenant_id,
            lob_id=item.lob_id,
            company_name=item.company_name.strip(),
            company_name_normalized=normalized,
            category=item.category,
            is_active=item.is_active,
        )
        db.add(exclusion)
        existing_normalized.add(normalized)
        created += 1

    db.commit()
    return {"created": created, "skipped": skipped, "total": len(data.companies)}


@router.put("/toggle-all")
async def toggle_all_exclusions(
    data: ExclusionToggleAll,
    db: Session = Depends(get_db),
    current_user=Depends(require_role([UserRole.ADMIN])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Toggle is_active for all exclusions (select all / unselect all).
    Optionally filter by lob_id or category."""
    if tenant_id is None:
        raise HTTPException(status_code=400, detail="No tenant context")

    q = db.query(CompanyExclusion).filter(CompanyExclusion.tenant_id == tenant_id)
    if data.lob_id is not None:
        q = q.filter(CompanyExclusion.lob_id == data.lob_id)
    if data.category is not None:
        q = q.filter(CompanyExclusion.category == data.category)

    updated = q.update({"is_active": data.is_active}, synchronize_session="fetch")
    db.commit()
    return {"updated": updated, "is_active": data.is_active}


@router.put("/{exclusion_id}", response_model=ExclusionResponse)
async def update_exclusion(
    exclusion_id: int,
    data: ExclusionUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_role([UserRole.ADMIN])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Update a single exclusion (company name, category, or active status)."""
    if tenant_id is None:
        raise HTTPException(status_code=400, detail="No tenant context")

    exclusion = db.query(CompanyExclusion).filter(
        CompanyExclusion.exclusion_id == exclusion_id,
        CompanyExclusion.tenant_id == tenant_id,
    ).first()
    if not exclusion:
        raise HTTPException(status_code=404, detail="Exclusion not found")

    if data.company_name is not None:
        exclusion.company_name = data.company_name.strip()
        exclusion.company_name_normalized = normalize_company_for_exclusion(data.company_name)
    if data.category is not None:
        exclusion.category = data.category
    if data.is_active is not None:
        exclusion.is_active = data.is_active

    db.commit()
    db.refresh(exclusion)
    return exclusion


@router.delete("/{exclusion_id}")
async def delete_exclusion(
    exclusion_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_role([UserRole.ADMIN])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Delete a single exclusion."""
    if tenant_id is None:
        raise HTTPException(status_code=400, detail="No tenant context")

    exclusion = db.query(CompanyExclusion).filter(
        CompanyExclusion.exclusion_id == exclusion_id,
        CompanyExclusion.tenant_id == tenant_id,
    ).first()
    if not exclusion:
        raise HTTPException(status_code=404, detail="Exclusion not found")

    db.delete(exclusion)
    db.commit()
    return {"message": f"Exclusion for '{exclusion.company_name}' deleted"}


@router.delete("/bulk/delete")
async def bulk_delete_exclusions(
    data: ExclusionBulkDelete,
    db: Session = Depends(get_db),
    current_user=Depends(require_role([UserRole.ADMIN])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Bulk-delete exclusions by ID."""
    if tenant_id is None:
        raise HTTPException(status_code=400, detail="No tenant context")

    deleted = db.query(CompanyExclusion).filter(
        CompanyExclusion.exclusion_id.in_(data.exclusion_ids),
        CompanyExclusion.tenant_id == tenant_id,
    ).delete(synchronize_session="fetch")
    db.commit()
    return {"deleted": deleted}


@router.post("/upload-xlsx")
async def upload_xlsx_exclusions(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user=Depends(require_role([UserRole.ADMIN])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
    lob_id: Optional[int] = Query(None),
):
    """Upload an Excel (.xlsx) file to bulk-import excluded companies.
    Expects column A = Agency Name, column C = Category (optional)."""
    if tenant_id is None:
        raise HTTPException(status_code=400, detail="No tenant context")

    if not file.filename.endswith(('.xlsx', '.xls')):
        raise HTTPException(status_code=400, detail="Only .xlsx files are supported")

    import tempfile
    import openpyxl

    # Save uploaded file to temp
    content = await file.read()
    with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        wb = openpyxl.load_workbook(tmp_path, read_only=True)
        ws = wb.active

        existing_normalized = set(
            r[0] for r in db.query(CompanyExclusion.company_name_normalized)
            .filter(CompanyExclusion.tenant_id == tenant_id)
            .all()
        )

        created = 0
        skipped = 0
        for row in ws.iter_rows(min_row=2, values_only=True):
            company_name = row[0] if row else None
            category = row[2] if len(row) > 2 else None

            if not company_name:
                continue

            company_name = str(company_name).strip()
            normalized = normalize_company_for_exclusion(company_name)

            if not normalized or normalized in existing_normalized:
                skipped += 1
                continue

            exclusion = CompanyExclusion(
                tenant_id=tenant_id,
                lob_id=lob_id,
                company_name=company_name,
                company_name_normalized=normalized,
                category=str(category).strip() if category else None,
                is_active=True,
            )
            db.add(exclusion)
            existing_normalized.add(normalized)
            created += 1

        db.commit()
        wb.close()
        return {"created": created, "skipped": skipped, "filename": file.filename}
    except Exception as e:
        db.rollback()
        logger.error("Excel upload failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to process file: {str(e)}")
    finally:
        os.unlink(tmp_path)
