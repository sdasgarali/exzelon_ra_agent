"""AI ICP Wizard endpoints — generate and manage Ideal Customer Profiles."""
import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List

from app.db.base import get_db
from app.api.deps.auth import get_current_user
from app.db.models.user import User
from app.db.models.icp_profile import ICPProfile

router = APIRouter(prefix="/icp", tags=["ICP Wizard"])


class GenerateICPRequest(BaseModel):
    company_description: str
    offering: str
    pain_points: str


class SaveICPRequest(BaseModel):
    name: str
    description: Optional[str] = None
    industries: List[str] = []
    job_titles: List[str] = []
    states: List[str] = []
    company_sizes: List[str] = []


@router.post("/generate")
def generate_icp(
    body: GenerateICPRequest,
    current_user: User = Depends(get_current_user),
):
    """AI-generate an Ideal Customer Profile from business description."""
    from app.services.ai_icp_wizard import generate_icp as gen_icp
    result = gen_icp(
        company_desc=body.company_description,
        offering=body.offering,
        pain_points=body.pain_points,
    )
    return result


@router.post("/profiles")
def save_icp_profile(
    body: SaveICPRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Save an ICP profile."""
    profile = ICPProfile(
        name=body.name,
        description=body.description,
        industries_json=json.dumps(body.industries),
        job_titles_json=json.dumps(body.job_titles),
        states_json=json.dumps(body.states),
        company_sizes_json=json.dumps(body.company_sizes),
        user_id=current_user.user_id,
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)

    return {
        "icp_id": profile.icp_id,
        "name": profile.name,
        "industries": body.industries,
        "job_titles": body.job_titles,
        "states": body.states,
        "company_sizes": body.company_sizes,
    }


@router.get("/profiles")
def list_icp_profiles(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all ICP profiles."""
    profiles = db.query(ICPProfile).filter(
        ICPProfile.is_archived == False,
    ).order_by(ICPProfile.created_at.desc()).all()

    result = []
    for p in profiles:
        result.append({
            "icp_id": p.icp_id,
            "name": p.name,
            "description": p.description,
            "industries": json.loads(p.industries_json) if p.industries_json else [],
            "job_titles": json.loads(p.job_titles_json) if p.job_titles_json else [],
            "states": json.loads(p.states_json) if p.states_json else [],
            "company_sizes": json.loads(p.company_sizes_json) if p.company_sizes_json else [],
            "user_id": p.user_id,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        })
    return result


@router.delete("/profiles/{icp_id}")
def delete_icp_profile(
    icp_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete an ICP profile."""
    profile = db.query(ICPProfile).filter(
        ICPProfile.icp_id == icp_id,
        ICPProfile.is_archived == False,
    ).first()
    if not profile:
        raise HTTPException(status_code=404, detail="ICP profile not found")

    profile.is_archived = True
    db.commit()
    return {"message": "Deleted", "icp_id": icp_id}
