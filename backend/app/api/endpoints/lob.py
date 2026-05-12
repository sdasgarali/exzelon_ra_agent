"""Line of Business (LOB) API endpoints."""
import json
import re
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps.database import get_db
from app.api.deps.auth import get_current_active_user, get_current_tenant_id
from app.db.models.user import User
from app.db.models.line_of_business import LineOfBusiness, LOBType, LOBStatus
from app.db.query_helpers import tenant_filter

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


# ── LOB Type Metadata ─────────────────────────────────────────

LOB_TYPE_META = {
    LOBType.STAFFING: {
        "label": "Staffing & Recruiting",
        "description": "Job board lead sourcing, hiring decision-maker targeting, staffing outreach",
        "default_color": "#1A3C6E",
        "default_icon": "briefcase",
    },
    LOBType.RCM: {
        "label": "Revenue Cycle Management",
        "description": "Healthcare provider targeting, medical billing/coding services outreach",
        "default_color": "#10B981",
        "default_icon": "heart-pulse",
    },
    LOBType.SOFTWARE_DEV: {
        "label": "Software Development",
        "description": "Tech company prospecting, CTO/VP Engineering targeting, dev services outreach",
        "default_color": "#6366F1",
        "default_icon": "code",
    },
    LOBType.AI_SERVICES: {
        "label": "AI & Agent Services",
        "description": "AI adoption signal tracking, innovation leader targeting, AI services outreach",
        "default_color": "#F59E0B",
        "default_icon": "brain",
    },
    LOBType.DIGITAL_MARKETING: {
        "label": "Digital Marketing",
        "description": "Website audit-based prospecting, SEO/SEM gap analysis, marketing services outreach",
        "default_color": "#EC4899",
        "default_icon": "megaphone",
    },
    LOBType.CUSTOM: {
        "label": "Custom",
        "description": "User-defined line of business with custom configuration",
        "default_color": "#8B5CF6",
        "default_icon": "settings",
    },
}


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


# ── Endpoints ──────────────────────────────────────────────────

@router.get("/column-config/{lob_type}")
async def get_column_config(lob_type: str):
    """Return per-LOB column configuration for the leads table UI."""
    config = LOB_COLUMN_CONFIG.get(lob_type)
    if config is None:
        # Fall back to staffing defaults for unknown types (including 'custom')
        config = LOB_COLUMN_CONFIG["staffing"]
    return config


@router.get("/types", response_model=List[LOBTypeInfo])
async def list_lob_types():
    """List available LOB types with metadata."""
    return [
        {
            "lob_type": lob_type.value,
            "label": meta["label"],
            "description": meta["description"],
            "default_color": meta["default_color"],
            "default_icon": meta["default_icon"],
        }
        for lob_type, meta in LOB_TYPE_META.items()
    ]


@router.get("/", response_model=List[LOBResponse])
async def list_lobs(
    status_filter: Optional[str] = Query(None, alias="status"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """List all LOBs for the current tenant."""
    query = db.query(LineOfBusiness).filter(LineOfBusiness.is_archived == False)
    query = tenant_filter(query, LineOfBusiness, tenant_id)

    if status_filter:
        query = query.filter(LineOfBusiness.status == status_filter)

    query = query.order_by(LineOfBusiness.is_default.desc(), LineOfBusiness.name)
    lobs = query.all()
    return [_to_response(lob) for lob in lobs]


@router.post("/", response_model=LOBResponse, status_code=status.HTTP_201_CREATED)
async def create_lob(
    payload: LOBCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Create a new Line of Business."""
    if tenant_id is None:
        raise HTTPException(status_code=400, detail="Tenant context required")

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
    current_user: User = Depends(get_current_active_user),
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
    current_user: User = Depends(get_current_active_user),
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


@router.post("/{lob_id}/set-default", response_model=LOBResponse)
async def set_default_lob(
    lob_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
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
