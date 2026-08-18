"""Password reset service for forgot-password flow."""
import re
from datetime import datetime
from sqlalchemy.orm import Session
import structlog

from app.core.config import settings
from app.core.security import (
    create_password_reset_token,
    decode_password_reset_token,
    get_password_hash,
)
from app.db.models.user import User

logger = structlog.get_logger()


def _send_email(to_email: str, subject: str, html_body: str) -> bool:
    """Send an email via SMTP. Reuses the same SMTP pattern as email_verification."""
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    if not settings.SMTP_HOST or not settings.SMTP_USER:
        logger.warning("SMTP not configured, skipping password reset email", to=to_email)
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

        logger.info("Password reset email sent", to=to_email)
        return True
    except Exception as e:
        logger.error("Failed to send password reset email", to=to_email, error=str(e))
        return False


def generate_and_send_reset(email: str, db: Session) -> bool:
    """Generate a reset token and send password reset email.

    Always returns True to prevent email enumeration (caller always returns 200).
    """
    user = db.query(User).filter(User.email == email).first()
    if not user or not user.is_active:
        # Don't reveal whether account exists
        logger.info("Password reset requested for unknown/inactive email", email=email)
        return True

    token = create_password_reset_token(email=user.email)
    user.password_reset_token = token
    user.password_reset_sent_at = datetime.utcnow()
    db.commit()

    # Build frontend reset URL
    base_url = settings.EFFECTIVE_BASE_URL
    frontend_url = base_url.replace("/api/v1", "").replace(":8000", ":3000")
    if "ra.partnerwithus.tech" in base_url:
        frontend_url = "https://ra.partnerwithus.tech"
    reset_url = f"{frontend_url}/reset-password?token={token}"

    html_body = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <h2 style="color: #2563eb;">Reset Your Password</h2>
        <p>Hi {user.full_name or 'there'},</p>
        <p>We received a request to reset your password. Click the button below to set a new password:</p>
        <div style="text-align: center; margin: 30px 0;">
            <a href="{reset_url}"
               style="background-color: #2563eb; color: white; padding: 12px 30px; text-decoration: none;
                      border-radius: 8px; font-weight: bold; display: inline-block;">
                Reset Password
            </a>
        </div>
        <p style="color: #666; font-size: 14px;">
            This link expires in 1 hour. If you didn't request a password reset, you can safely ignore this email.
        </p>
        <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;" />
        <p style="color: #999; font-size: 12px;">NeuraLeads &mdash; AI-Powered Sales Outreach Platform</p>
    </div>
    """

    from app.services.system_mailer import send_system_email
    send_system_email(db, getattr(user, "tenant_id", None), user.email, "Reset your NeuraLeads password", html_body)
    return True


def validate_password_policy(password: str) -> str | None:
    """Validate password meets policy. Returns error message or None if valid."""
    if len(password) < 8:
        return "Password must be at least 8 characters."
    if not re.search(r"[A-Z]", password):
        return "Password must contain at least one uppercase letter."
    if not re.search(r"\d", password):
        return "Password must contain at least one digit."
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
        return "Password must contain at least one special character."
    return None


def reset_password(token: str, new_password: str, db: Session) -> tuple[bool, str]:
    """Validate token and reset user's password.

    Returns:
        (success: bool, message: str)
    """
    payload = decode_password_reset_token(token)
    if not payload:
        return False, "Invalid or expired reset link. Please request a new one."

    email = payload.get("sub")
    if not email:
        return False, "Invalid reset token."

    user = db.query(User).filter(User.email == email).first()
    if not user:
        return False, "Invalid reset token."

    # Check token matches what we stored (prevents reuse of old tokens)
    if user.password_reset_token != token:
        return False, "This reset link has already been used. Please request a new one."

    # Enforce password policy
    policy_error = validate_password_policy(new_password)
    if policy_error:
        return False, policy_error

    # Reset password
    user.password_hash = get_password_hash(new_password)
    user.password_reset_token = None
    user.password_reset_sent_at = None
    # Also unlock the account if it was locked
    user.failed_login_count = 0
    user.locked_until = None
    db.commit()

    logger.info("Password reset successful", email=email)
    return True, "Password reset successfully. You can now sign in with your new password."
