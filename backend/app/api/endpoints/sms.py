"""SMS outreach endpoints -- leverages existing Twilio adapter."""
import structlog
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps.database import get_db
from app.api.deps.auth import get_current_active_user, require_role, get_current_tenant_id
from app.db.models.user import User, UserRole
from app.core.config import settings

logger = structlog.get_logger()

router = APIRouter(prefix="/sms", tags=["sms"])


class SMSSend(BaseModel):
    to_phone: str
    message: str
    contact_id: Optional[int] = None
    campaign_id: Optional[int] = None


class SMSBulkSend(BaseModel):
    phone_numbers: list  # list of {to_phone, message, contact_id}


@router.post("/send")
def send_sms(
    data: SMSSend,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([UserRole.ADMIN, UserRole.BDM])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Send an SMS message via Twilio."""
    if not getattr(settings, "TWILIO_ACCOUNT_SID", None):
        raise HTTPException(status_code=400, detail="Twilio is not configured")

    try:
        from app.services.adapters.communications.twilio_adapter import TwilioAdapter

        adapter = TwilioAdapter(
            account_sid=getattr(settings, "TWILIO_ACCOUNT_SID", ""),
            auth_token=getattr(settings, "TWILIO_AUTH_TOKEN", ""),
            from_number=getattr(settings, "TWILIO_FROM_NUMBER", ""),
        )
        result = adapter.send_sms(to_number=data.to_phone, body=data.message)

        if not result.get("success"):
            raise HTTPException(
                status_code=500,
                detail=f"SMS send failed: {result.get('error', 'Unknown error')}",
            )

        # Record credit usage
        try:
            from app.services.credit_metering import record_usage

            record_usage(
                db,
                tenant_id=tenant_id or 1,
                usage_type="sms_send",
                credits=1.0,
                description=f"SMS to {data.to_phone}",
                user_id=user.user_id,
                reference_id=str(data.contact_id) if data.contact_id else None,
            )
        except Exception:
            pass

        logger.info("sms_sent", to=data.to_phone, user=user.email)
        return {
            "success": True,
            "sid": result.get("sid"),
            "status": result.get("status", "sent"),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("sms_send_error", error=str(e))
        raise HTTPException(status_code=500, detail=f"SMS send failed: {str(e)}")


@router.get("/status")
def sms_status(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Check if SMS (Twilio) is configured."""
    return {
        "configured": bool(getattr(settings, "TWILIO_ACCOUNT_SID", None)),
        "provider": "twilio",
        "from_number": getattr(settings, "TWILIO_FROM_NUMBER", None),
    }
