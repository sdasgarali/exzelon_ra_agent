"""AI Sequence Generator endpoint — generate multi-step email sequences."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional

from app.api.deps.auth import get_current_user, get_current_tenant_id
from app.db.base import get_db
from app.db.models.user import User

router = APIRouter(prefix="/sequence-generator", tags=["Sequence Generator"])


class GenerateSequenceRequest(BaseModel):
    goal: str
    product: str
    tone: str = "professional"  # professional, casual, urgent, friendly
    num_steps: int = 4


@router.post("/generate")
def generate_sequence(
    body: GenerateSequenceRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """AI-generate a multi-step email campaign sequence."""
    from app.services.ai_sequence_generator import generate_sequence as gen_seq
    steps = gen_seq(
        goal=body.goal,
        product=body.product,
        tone=body.tone,
        num_steps=body.num_steps,
        db=db,
        tenant_id=tenant_id,
    )
    return {"steps": steps, "total": len(steps)}
