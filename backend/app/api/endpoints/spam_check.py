"""Spam check endpoint — score email content for spam triggers."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps.auth import get_current_user
from app.db.models.user import User

router = APIRouter(prefix="/spam-check", tags=["Spam Check"])


class SpamCheckRequest(BaseModel):
    subject: str = ""
    body_html: str = ""


@router.post("")
def check_spam(
    body: SpamCheckRequest,
    current_user: User = Depends(get_current_user),
):
    """Check email content for spam trigger words and patterns.

    Returns a score (0-100), grade, and flagged words with severity.
    """
    from app.services.spam_checker import check_spam_score
    return check_spam_score(subject=body.subject, body_html=body.body_html)
