"""Email verification service for signup flow."""
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from sqlalchemy.orm import Session
import structlog

from app.core.config import settings
from app.core.security import create_verification_token, decode_verification_token
from app.db.models.user import User
from app.db.models.tenant import Tenant

logger = structlog.get_logger()


def _send_email(to_email: str, subject: str, html_body: str) -> bool:
    """Send an email via SMTP. Returns True on success, False on failure."""
    if not settings.SMTP_HOST or not settings.SMTP_USER:
        logger.warning("SMTP not configured, skipping email send", to=to_email)
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = settings.SMTP_USER
        msg["To"] = to_email
        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail(settings.SMTP_USER, to_email, msg.as_string())

        logger.info("Verification email sent", to=to_email)
        return True
    except Exception as e:
        logger.error("Failed to send verification email", to=to_email, error=str(e))
        return False


def send_verification_email(user: User, db: Session) -> bool:
    """Generate a verification token and send verification email to user.

    Args:
        user: The unverified User record.
        db: Database session.

    Returns:
        True if email sent (or SMTP not configured -- auto-verify in dev), False on error.
    """
    token = create_verification_token(user_id=user.user_id)
    user.verification_token = token
    user.verification_sent_at = datetime.utcnow()
    db.commit()

    base_url = settings.EFFECTIVE_BASE_URL
    # Use frontend URL for verification link (not API)
    frontend_url = base_url.replace("/api/v1", "").replace(":8000", ":3000")
    if "ra.partnerwithus.tech" in base_url:
        frontend_url = "https://ra.partnerwithus.tech"
    verify_url = f"{frontend_url}/verify?token={token}"

    html_body = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <h2 style="color: #2563eb;">Welcome to NeuraLeads!</h2>
        <p>Hi {user.full_name or 'there'},</p>
        <p>Thanks for signing up. Please verify your email address by clicking the button below:</p>
        <div style="text-align: center; margin: 30px 0;">
            <a href="{verify_url}"
               style="background-color: #2563eb; color: white; padding: 12px 30px; text-decoration: none;
                      border-radius: 8px; font-weight: bold; display: inline-block;">
                Verify Email Address
            </a>
        </div>
        <p style="color: #666; font-size: 14px;">
            This link expires in 24 hours. If you didn't sign up for NeuraLeads, you can ignore this email.
        </p>
        <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;" />
        <p style="color: #999; font-size: 12px;">NeuraLeads &mdash; AI-Powered Sales Outreach Platform</p>
    </div>
    """

    sent = _send_email(user.email, "Verify your NeuraLeads email", html_body)

    if not sent and settings.DEBUG:
        # In dev mode without SMTP, auto-verify for convenience
        logger.warning("Auto-verifying user (dev mode, no SMTP)", email=user.email)
        user.is_verified = True
        user.verification_token = None
        db.commit()
        return True

    return sent


def verify_user_email(token: str, db: Session) -> bool:
    """Verify a user's email using the verification token.

    Args:
        token: The JWT verification token from the email link.
        db: Database session.

    Returns:
        True if verified successfully, False if token is invalid/expired.
    """
    payload = decode_verification_token(token)
    if payload is None:
        return False

    user_id = payload.get("user_id")
    if user_id is None:
        return False

    user = db.query(User).filter(User.user_id == user_id).first()
    if user is None:
        return False

    if user.is_verified:
        return True  # Already verified -- idempotent

    user.is_verified = True
    user.verification_token = None
    db.commit()

    logger.info("User email verified", user_id=user_id, email=user.email)

    # Seed demo data for starter plan tenants
    if user.tenant_id:
        try:
            from app.services.demo_seeder import seed_demo_data
            from app.db.models.tenant import TenantPlan
            tenant = db.query(Tenant).filter(Tenant.tenant_id == user.tenant_id).first()
            if tenant and tenant.plan == TenantPlan.STARTER:
                seed_demo_data(user.tenant_id, db)
        except Exception as e:
            logger.warning("Failed to seed demo data on verify", error=str(e))

    return True
