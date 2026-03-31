"""Authentication endpoints."""
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.api.deps import get_db, get_current_active_user
from app.api.deps.plan_limits import check_plan_limit
from app.core.security import verify_password, get_password_hash, create_access_token
from app.core.config import settings
from app.db.models.user import User, UserRole
from app.db.models.login_history import LoginHistory
from app.schemas.user import UserCreate, UserResponse, Token
from app.schemas.tenant import SignupRequest, SignupResponse, VerifyResponse
from app.services.audit_helper import write_audit_log, get_client_ip

limiter = Limiter(key_func=get_remote_address, swallow_errors=True)
router = APIRouter(prefix="/auth", tags=["Authentication"])

# Lockout constants
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_DURATION_MINUTES = 15


def _record_login(db: Session, *, email: str, success: bool, user: User = None,
                   failure_reason: str = None, ip: str = None, ua: str = None):
    """Record a login attempt in login_history."""
    entry = LoginHistory(
        tenant_id=user.tenant_id if user else None,
        user_id=user.user_id if user else None,
        email_attempted=email,
        success=success,
        failure_reason=failure_reason,
        ip_address=ip,
        user_agent=ua,
    )
    db.add(entry)


@router.post("/login", response_model=Token)
@limiter.limit("5/minute")
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    """Authenticate user and return JWT token."""
    ip = get_client_ip(request)
    ua = (request.headers.get("User-Agent") or "")[:500]
    email = form_data.username

    user = db.query(User).filter(User.email == email).first()

    # Check if account is locked
    if user and user.locked_until and user.locked_until > datetime.utcnow():
        _record_login(db, email=email, success=False, user=user,
                       failure_reason="locked", ip=ip, ua=ua)
        db.commit()
        raise HTTPException(
            status_code=423,
            detail=f"Account locked due to too many failed attempts. Try again after {user.locked_until.strftime('%H:%M UTC')}.",
        )

    # Check credentials
    if not user or not verify_password(form_data.password, user.password_hash):
        if user:
            user.failed_login_count = (user.failed_login_count or 0) + 1
            if user.failed_login_count >= MAX_FAILED_ATTEMPTS:
                user.locked_until = datetime.utcnow() + timedelta(minutes=LOCKOUT_DURATION_MINUTES)
        _record_login(db, email=email, success=False, user=user,
                       failure_reason="invalid_credentials", ip=ip, ua=ua)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        _record_login(db, email=email, success=False, user=user,
                       failure_reason="inactive", ip=ip, ua=ua)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user account"
        )

    # Check email verification (skip for pre-existing users without tenant)
    if not user.is_verified and user.tenant_id is not None:
        _record_login(db, email=email, success=False, user=user,
                       failure_reason="unverified", ip=ip, ua=ua)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email not verified. Check your inbox for the verification link."
        )

    # Success — reset lockout counters
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = datetime.utcnow()

    _record_login(db, email=email, success=True, user=user, ip=ip, ua=ua)
    write_audit_log(db, tenant_id=user.tenant_id or 0, entity_type="auth",
                    entity_id=user.user_id, action="login_success",
                    changed_by=user.email, notes=f"IP: {ip}")
    db.commit()

    # Build token with tenant context
    token_data = {
        "sub": user.email,
        "role": user.role.value if user.role else None,
        "tenant_id": user.tenant_id,
        "plan": user.tenant.plan.value if user.tenant else None,
    }

    access_token = create_access_token(
        data=token_data,
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    return Token(
        access_token=access_token,
        user=UserResponse.model_validate(user)
    )


@router.post("/signup", response_model=SignupResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/hour")
async def signup(
    request: Request,
    data: SignupRequest,
    db: Session = Depends(get_db),
):
    """Self-service signup: create tenant + admin user + send verification email."""
    from app.services.tenant_service import create_tenant_for_signup
    from app.services.email_verification import send_verification_email

    # Check if email already exists
    existing = db.query(User).filter(User.email == data.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    # Create tenant
    tenant = create_tenant_for_signup(data.company_name, db)

    # Create user as admin of the new tenant (unverified)
    user = User(
        email=data.email,
        password_hash=get_password_hash(data.password),
        full_name=data.full_name,
        role=UserRole.ADMIN,
        tenant_id=tenant.tenant_id,
        is_active=True,
        is_verified=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    ip = get_client_ip(request)
    write_audit_log(db, tenant_id=tenant.tenant_id, entity_type="auth",
                    entity_id=user.user_id, action="signup",
                    changed_by=user.email, notes=f"company={data.company_name}, IP: {ip}")
    db.commit()

    # Send verification email
    send_verification_email(user, db)

    return SignupResponse(
        message="Verification email sent. Check your inbox.",
        user_id=user.user_id,
    )


@router.get("/verify", response_model=VerifyResponse)
async def verify_email(
    token: str = Query(..., description="Verification token from email"),
    db: Session = Depends(get_db),
):
    """Verify user email address via token link."""
    from app.services.email_verification import verify_user_email

    success = verify_user_email(token, db)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification link. Please request a new one."
        )

    return VerifyResponse(message="Email verified successfully!", verified=True)


class ResendRequest(BaseModel):
    email: EmailStr


@router.post("/resend-verification")
@limiter.limit("3/hour")
async def resend_verification(
    request: Request,
    data: ResendRequest,
    db: Session = Depends(get_db),
):
    """Resend verification email. Returns 200 regardless to prevent email enumeration."""
    from app.services.email_verification import send_verification_email

    user = db.query(User).filter(User.email == data.email, User.is_verified == False).first()
    if user:
        send_verification_email(user, db)

    return {"message": "If that email is registered and unverified, a new verification link has been sent."}


@router.post("/register", response_model=UserResponse)
async def register(
    user_in: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Create a new user within the current tenant (admin use only).

    NOTE: This is NOT for self-service signup. Use /auth/signup for that.
    This endpoint requires authentication and creates users within the
    caller's tenant with viewer role.
    """
    # Only admins can create users
    if current_user.role not in [UserRole.SUPER_ADMIN, UserRole.ADMIN]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")

    check_plan_limit(db, current_user.tenant_id, "users")

    # Check if email exists
    existing_user = db.query(User).filter(User.email == user_in.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    # SECURITY FIX: Ignore role from request body -- always create as viewer
    user = User(
        email=user_in.email,
        password_hash=get_password_hash(user_in.password),
        full_name=user_in.full_name,
        role=UserRole.VIEWER,
        tenant_id=current_user.tenant_id,
        is_active=True,
        is_verified=True,  # Admin-created users are pre-verified
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return UserResponse.model_validate(user)


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_active_user)):
    """Get current authenticated user."""
    return UserResponse.model_validate(current_user)


@router.post("/logout")
async def logout(current_user: User = Depends(get_current_active_user)):
    """Logout user (client should discard token)."""
    return {"message": "Successfully logged out"}
