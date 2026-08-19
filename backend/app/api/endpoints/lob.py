"""Line of Business (LOB) API endpoints."""
import json
import re
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps.database import get_db
from app.api.deps.auth import get_current_active_user, get_current_tenant_id, require_role
from app.db.models.user import User, UserRole
from app.db.models.line_of_business import LineOfBusiness, LOBType, LOBStatus
from app.db.models.tenant_lob_assignment import TenantLOBAssignment
from app.db.query_helpers import tenant_filter
from app.core.lob_defaults import LOB_TYPE_META as _LOB_TYPE_META_STR

router = APIRouter(prefix="/lob", tags=["Lines of Business"])


# ── Schemas ────────────────────────────────────────────────────

class LOBCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    lob_type: LOBType
    description: Optional[str] = None
    lead_source_config: Optional[dict] = None
    icp_config: Optional[dict] = None
    business_rules: Optional[dict] = None
    prompt_profile: Optional[dict] = None
    target_industries: Optional[List[str]] = None
    target_job_titles: Optional[List[str]] = None
    exclude_keywords: Optional[List[str]] = None
    is_default: bool = False
    color: Optional[str] = None
    icon: Optional[str] = None


class LOBUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    lead_source_config: Optional[dict] = None
    icp_config: Optional[dict] = None
    business_rules: Optional[dict] = None
    prompt_profile: Optional[dict] = None
    target_industries: Optional[List[str]] = None
    target_job_titles: Optional[List[str]] = None
    exclude_keywords: Optional[List[str]] = None
    status: Optional[LOBStatus] = None
    color: Optional[str] = None
    icon: Optional[str] = None


class LOBResponse(BaseModel):
    lob_id: int
    tenant_id: int
    name: str
    slug: str
    lob_type: str
    description: Optional[str] = None
    lead_source_config: Optional[dict] = None
    icp_config: Optional[dict] = None
    business_rules: Optional[dict] = None
    prompt_profile: Optional[dict] = None
    target_industries: Optional[List[str]] = None
    target_job_titles: Optional[List[str]] = None
    exclude_keywords: Optional[List[str]] = None
    is_default: bool
    status: str
    color: Optional[str] = None
    icon: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True


class LOBTypeInfo(BaseModel):
    lob_type: str
    label: str
    description: str
    default_color: str
    default_icon: str


# ── Helpers ────────────────────────────────────────────────────

def _slugify(text: str) -> str:
    """Convert text to URL-friendly slug."""
    slug = text.lower().strip()
    slug = re.sub(r'[^\w\s-]', '', slug)
    slug = re.sub(r'[\s_]+', '-', slug)
    slug = re.sub(r'-+', '-', slug)
    return slug.strip('-')


def _json_loads_safe(value: Optional[str]):
    """Safely parse JSON string, return None on failure."""
    if value is None:
        return None
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return None


def _to_response(lob: LineOfBusiness) -> dict:
    """Convert LOB model to response dict."""
    return {
        "lob_id": lob.lob_id,
        "tenant_id": lob.tenant_id,
        "name": lob.name,
        "slug": lob.slug,
        "lob_type": lob.lob_type.value if isinstance(lob.lob_type, LOBType) else lob.lob_type,
        "description": lob.description,
        "lead_source_config": _json_loads_safe(lob.lead_source_config),
        "icp_config": _json_loads_safe(lob.icp_config),
        "business_rules": _json_loads_safe(lob.business_rules),
        "prompt_profile": _json_loads_safe(lob.prompt_profile),
        "target_industries": _json_loads_safe(lob.target_industries_json),
        "target_job_titles": _json_loads_safe(lob.target_job_titles_json),
        "exclude_keywords": _json_loads_safe(lob.exclude_keywords_json),
        "is_default": lob.is_default,
        "status": lob.status.value if isinstance(lob.status, LOBStatus) else lob.status,
        "color": lob.color,
        "icon": lob.icon,
        "created_at": lob.created_at.isoformat() if lob.created_at else None,
        "updated_at": lob.updated_at.isoformat() if lob.updated_at else None,
    }


# ── LOB Type Metadata (enum-keyed, built from shared module) ──

LOB_TYPE_META = {}
for _lt in LOBType:
    if _lt.value in _LOB_TYPE_META_STR:
        LOB_TYPE_META[_lt] = _LOB_TYPE_META_STR[_lt.value]


# ── Column Configuration per LOB type ─────────────────────────

LOB_COLUMN_CONFIG = {
    "staffing": {
        "label_overrides": {},
        "hidden_columns": [],
        "metadata_columns": [],
        "filters": ["status", "source", "state", "industry", "employment_type", "salary"],
    },
    "rcm": {
        "label_overrides": {
            "job_title": "Specialty",
            "posting_date": "Registration Date",
            "job_link": "NPI Lookup",
            "client_name": "Practice Name",
        },
        "hidden_columns": ["salary_min", "salary_max", "employment_type"],
        "metadata_columns": [
            {"key": "npi_number", "label": "NPI #", "type": "text"},
            {"key": "provider_count", "label": "Providers", "type": "number"},
            {"key": "primary_specialty", "label": "Primary Specialty", "type": "text"},
            {"key": "phone", "label": "Phone", "type": "phone"},
        ],
        "filters": ["status", "source", "state"],
    },
    "software_dev": {
        "label_overrides": {
            "job_title": "Category",
            "posting_date": "Funding Date",
            "job_link": "Profile URL",
        },
        "hidden_columns": ["salary_min", "salary_max", "employment_type"],
        "metadata_columns": [
            {"key": "last_funding_type", "label": "Funding Stage", "type": "badge"},
            {"key": "funding_total_usd", "label": "Total Funding", "type": "currency"},
            {"key": "employee_count", "label": "Employees", "type": "number"},
            {"key": "tech_stack", "label": "Tech Stack", "type": "tags"},
        ],
        "filters": ["status", "source", "state", "industry"],
    },
    "ai_services": {
        "label_overrides": {
            "job_title": "AI Category",
            "posting_date": "Founded Date",
            "job_link": "Profile URL",
        },
        "hidden_columns": ["salary_min", "salary_max", "employment_type"],
        "metadata_columns": [
            {"key": "categories", "label": "Categories", "type": "tags"},
            {"key": "public_repos", "label": "Repos", "type": "number"},
            {"key": "employee_count", "label": "Team Size", "type": "number"},
        ],
        "filters": ["status", "source", "state"],
    },
    "digital_marketing": {
        "label_overrides": {
            "job_title": "Domain",
            "posting_date": "Audit Date",
            "job_link": "Website",
            "client_name": "Business",
        },
        "hidden_columns": ["salary_min", "salary_max", "employment_type"],
        "metadata_columns": [
            {"key": "performance_score", "label": "Performance", "type": "score"},
            {"key": "seo_score", "label": "SEO Score", "type": "score"},
            {"key": "accessibility_score", "label": "Accessibility", "type": "score"},
            {"key": "best_practices_score", "label": "Best Practices", "type": "score"},
        ],
        "filters": ["status", "source", "state"],
    },
}


# ── Assignment helpers ─────────────────────────────────────────

def _get_assigned_lob_types(db: Session, tenant_id: Optional[int]) -> Optional[set]:
    """Return the set of assigned LOB type strings for a tenant.

    Returns None if tenant has no assignment records (backward compatible: no filtering).
    """
    if tenant_id is None:
        return None  # super admin — no filtering
    assignments = (
        db.query(TenantLOBAssignment.lob_type)
        .filter(
            TenantLOBAssignment.tenant_id == tenant_id,
            TenantLOBAssignment.is_archived == False,
        )
        .all()
    )
    if not assignments:
        return None  # no assignments configured — show all (backward compatible)
    return {a.lob_type for a in assignments}


# ── Endpoints ──────────────────────────────────────────────────

@router.get("/column-config/{lob_type}")
async def get_column_config(
    lob_type: str,
    current_user: User = Depends(get_current_active_user),
):
    """Return per-LOB column configuration for the leads table UI."""
    config = LOB_COLUMN_CONFIG.get(lob_type)
    if config is None:
        # Fall back to staffing defaults for unknown types (including 'custom')
        config = LOB_COLUMN_CONFIG["staffing"]
    return config


@router.get("/types", response_model=List[LOBTypeInfo])
async def list_lob_types(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """List available LOB types with metadata, filtered by tenant assignments."""
    assigned = _get_assigned_lob_types(db, tenant_id)
    result = []
    for lob_type, meta in LOB_TYPE_META.items():
        if assigned is not None and lob_type.value not in assigned:
            continue
        result.append({
            "lob_type": lob_type.value,
            "label": meta["label"],
            "description": meta["description"],
            "default_color": meta["default_color"],
            "default_icon": meta["default_icon"],
        })
    return result


@router.get("/", response_model=List[LOBResponse])
async def list_lobs(
    status_filter: Optional[str] = Query(None, alias="status"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """List all LOBs for the current tenant, filtered by LOB assignments."""
    query = db.query(LineOfBusiness).filter(LineOfBusiness.is_archived == False)
    query = tenant_filter(query, LineOfBusiness, tenant_id)

    # Filter by tenant LOB assignments (if configured)
    assigned = _get_assigned_lob_types(db, tenant_id)
    if assigned is not None:
        assigned_enums = []
        for v in assigned:
            try:
                assigned_enums.append(LOBType(v))
            except ValueError:
                pass
        if assigned_enums:
            query = query.filter(LineOfBusiness.lob_type.in_(assigned_enums))

    if status_filter:
        query = query.filter(LineOfBusiness.status == status_filter)

    query = query.order_by(LineOfBusiness.is_default.desc(), LineOfBusiness.name)
    lobs = query.all()
    return [_to_response(lob) for lob in lobs]


@router.post("/", response_model=LOBResponse, status_code=status.HTTP_201_CREATED)
async def create_lob(
    payload: LOBCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.BDM])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Create a new Line of Business."""
    if tenant_id is None:
        raise HTTPException(status_code=400, detail="Tenant context required")

    # Check LOB assignment restrictions
    assigned = _get_assigned_lob_types(db, tenant_id)
    if assigned is not None:
        lob_type_val = payload.lob_type.value if hasattr(payload.lob_type, 'value') else str(payload.lob_type)
        if lob_type_val not in assigned:
            raise HTTPException(
                status_code=403,
                detail=f"LOB type '{lob_type_val}' is not assigned to this tenant",
            )

    slug = _slugify(payload.name)

    # Check for duplicate slug within tenant
    existing = (
        db.query(LineOfBusiness)
        .filter(
            LineOfBusiness.tenant_id == tenant_id,
            LineOfBusiness.slug == slug,
            LineOfBusiness.is_archived == False,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail=f"LOB with slug '{slug}' already exists")

    # If setting as default, unset other defaults
    if payload.is_default:
        db.query(LineOfBusiness).filter(
            LineOfBusiness.tenant_id == tenant_id,
        ).update({"is_default": False})

    meta = LOB_TYPE_META.get(payload.lob_type, LOB_TYPE_META[LOBType.CUSTOM])

    lob = LineOfBusiness(
        tenant_id=tenant_id,
        name=payload.name,
        slug=slug,
        lob_type=payload.lob_type,
        description=payload.description,
        lead_source_config=json.dumps(payload.lead_source_config) if payload.lead_source_config else None,
        icp_config=json.dumps(payload.icp_config) if payload.icp_config else None,
        business_rules=json.dumps(payload.business_rules) if payload.business_rules else None,
        prompt_profile=json.dumps(payload.prompt_profile) if payload.prompt_profile else None,
        target_industries_json=json.dumps(payload.target_industries) if payload.target_industries else None,
        target_job_titles_json=json.dumps(payload.target_job_titles) if payload.target_job_titles else None,
        exclude_keywords_json=json.dumps(payload.exclude_keywords) if payload.exclude_keywords else None,
        is_default=payload.is_default,
        color=payload.color or meta["default_color"],
        icon=payload.icon or meta["default_icon"],
    )
    db.add(lob)
    db.commit()
    db.refresh(lob)
    return _to_response(lob)


@router.get("/{lob_id}", response_model=LOBResponse)
async def get_lob(
    lob_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Get LOB details by ID."""
    query = db.query(LineOfBusiness).filter(
        LineOfBusiness.lob_id == lob_id,
        LineOfBusiness.is_archived == False,
    )
    query = tenant_filter(query, LineOfBusiness, tenant_id)
    lob = query.first()

    if not lob:
        raise HTTPException(status_code=404, detail="LOB not found")

    return _to_response(lob)


@router.put("/{lob_id}", response_model=LOBResponse)
async def update_lob(
    lob_id: int,
    payload: LOBUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.BDM])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Update an existing LOB."""
    query = db.query(LineOfBusiness).filter(
        LineOfBusiness.lob_id == lob_id,
        LineOfBusiness.is_archived == False,
    )
    query = tenant_filter(query, LineOfBusiness, tenant_id)
    lob = query.first()

    if not lob:
        raise HTTPException(status_code=404, detail="LOB not found")

    if payload.name is not None:
        lob.name = payload.name
        lob.slug = _slugify(payload.name)
    if payload.description is not None:
        lob.description = payload.description
    if payload.lead_source_config is not None:
        lob.lead_source_config = json.dumps(payload.lead_source_config)
    if payload.icp_config is not None:
        lob.icp_config = json.dumps(payload.icp_config)
    if payload.business_rules is not None:
        lob.business_rules = json.dumps(payload.business_rules)
    if payload.prompt_profile is not None:
        lob.prompt_profile = json.dumps(payload.prompt_profile)
    if payload.target_industries is not None:
        lob.target_industries_json = json.dumps(payload.target_industries)
    if payload.target_job_titles is not None:
        lob.target_job_titles_json = json.dumps(payload.target_job_titles)
    if payload.exclude_keywords is not None:
        lob.exclude_keywords_json = json.dumps(payload.exclude_keywords)
    if payload.status is not None:
        lob.status = payload.status
    if payload.color is not None:
        lob.color = payload.color
    if payload.icon is not None:
        lob.icon = payload.icon

    db.commit()
    db.refresh(lob)
    return _to_response(lob)


@router.delete("/{lob_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_lob(
    lob_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.BDM])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Soft-delete (archive) an LOB. Cannot delete the default LOB."""
    query = db.query(LineOfBusiness).filter(
        LineOfBusiness.lob_id == lob_id,
        LineOfBusiness.is_archived == False,
    )
    query = tenant_filter(query, LineOfBusiness, tenant_id)
    lob = query.first()

    if not lob:
        raise HTTPException(status_code=404, detail="LOB not found")

    if lob.is_default:
        raise HTTPException(status_code=400, detail="Cannot delete the default LOB. Set another LOB as default first.")

    lob.is_archived = True
    db.commit()


@router.get("/{lob_id}/intent-signals")
async def get_lob_intent_signals(
    lob_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Return configured + available intent signals for a LOB with their status."""
    query = db.query(LineOfBusiness).filter(
        LineOfBusiness.lob_id == lob_id,
        LineOfBusiness.is_archived == False,
    )
    query = tenant_filter(query, LineOfBusiness, tenant_id)
    lob = query.first()

    if not lob:
        raise HTTPException(status_code=404, detail="LOB not found")

    from app.services.intent_signal_monitor import get_available_signals, _default_signals_for_lob_type
    from app.core.settings_resolver import get_lob_config

    # Get configured signals
    lead_source_config = get_lob_config(db, lob_id, "lead_source_config") or {}
    configured_signals = lead_source_config.get("intent_signals", {})

    if not configured_signals:
        configured_signals = _default_signals_for_lob_type(
            lob.lob_type.value if isinstance(lob.lob_type, LOBType) else lob.lob_type
        )

    # Get available signals for this LOB type
    lob_type_str = lob.lob_type.value if isinstance(lob.lob_type, LOBType) else lob.lob_type
    available = get_available_signals(lob_type_str)

    # Merge status
    result = []
    for signal in available:
        signal_name = signal["name"]
        result.append({
            **signal,
            "configured": signal_name in configured_signals,
            "config": configured_signals.get(signal_name, {}),
        })

    return {
        "lob_id": lob_id,
        "lob_type": lob_type_str,
        "signals": result,
    }


@router.post("/{lob_id}/intent-signals/run")
async def run_lob_intent_signals(
    lob_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.BDM])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Manually trigger intent engine for a specific LOB."""
    query = db.query(LineOfBusiness).filter(
        LineOfBusiness.lob_id == lob_id,
        LineOfBusiness.is_archived == False,
    )
    query = tenant_filter(query, LineOfBusiness, tenant_id)
    lob = query.first()

    if not lob:
        raise HTTPException(status_code=404, detail="LOB not found")

    from app.services.intent_engine import run_intent_engine
    result = run_intent_engine(
        tenant_id=lob.tenant_id,
        lob_id=lob_id,
        schedule_type="manual",
    )

    return result


@router.post("/{lob_id}/set-default", response_model=LOBResponse)
async def set_default_lob(
    lob_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.BDM])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Set an LOB as the default for the tenant."""
    if tenant_id is None:
        raise HTTPException(status_code=400, detail="Tenant context required")

    query = db.query(LineOfBusiness).filter(
        LineOfBusiness.lob_id == lob_id,
        LineOfBusiness.is_archived == False,
    )
    query = tenant_filter(query, LineOfBusiness, tenant_id)
    lob = query.first()

    if not lob:
        raise HTTPException(status_code=404, detail="LOB not found")

    # Unset all others
    db.query(LineOfBusiness).filter(
        LineOfBusiness.tenant_id == tenant_id,
    ).update({"is_default": False})

    lob.is_default = True
    db.commit()
    db.refresh(lob)
    return _to_response(lob)
