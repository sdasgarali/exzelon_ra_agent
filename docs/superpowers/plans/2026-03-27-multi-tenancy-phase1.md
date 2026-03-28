# Multi-Tenancy Phase 1: Foundation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish the tenant model, email-verified signup, JWT tenant context, and tenant-aware auth dependency — the foundation all subsequent data isolation builds on.

**Architecture:** Enhance the existing (unused) Tenant model with plan tiers. Add tenant_id + verification fields to User. Create a new `/auth/signup` endpoint that creates Tenant + User + sends verification email. Embed tenant_id in JWT tokens. Create a `get_current_tenant_id()` dependency that all future endpoint retrofitting will use. Migrate existing data to Tenant #1.

**Tech Stack:** FastAPI, SQLAlchemy 2.0, PyJWT (jose), Argon2, SMTP (existing mailbox infra), Next.js 14, Zustand, Tailwind CSS

**Spec:** `docs/superpowers/specs/2026-03-27-multi-tenancy-design.md`

---

## File Structure

### New Files
| File | Responsibility |
|------|---------------|
| `backend/app/services/email_verification.py` | Generate verification tokens, send verification emails, verify tokens |
| `backend/app/services/tenant_service.py` | Create tenant, seed demo data, check plan limits |
| `backend/app/schemas/tenant.py` | Pydantic schemas for tenant + signup request/response |
| `backend/tests/unit/test_tenant_service.py` | Unit tests for tenant creation and plan limits |
| `backend/tests/unit/test_email_verification.py` | Unit tests for token generation and verification |
| `backend/tests/integration/test_auth_signup.py` | Integration tests for signup + verification + login flow |
| `frontend/src/app/signup/page.tsx` | Dedicated signup page with company name field |
| `frontend/src/app/verify/page.tsx` | Email verification landing page |

### Modified Files
| File | Changes |
|------|---------|
| `backend/app/db/models/tenant.py` | Add TenantPlan enum, max_users, max_leads fields, remove unused fields |
| `backend/app/db/models/user.py` | Add tenant_id FK, is_verified, verification_token, verification_sent_at |
| `backend/app/schemas/user.py` | Add tenant info to UserResponse, add SignupRequest schema |
| `backend/app/core/security.py` | Add tenant_id to JWT payload, add create_verification_token() |
| `backend/app/api/endpoints/auth.py` | Add /signup, /verify, /resend-verification endpoints; fix role injection in /register |
| `backend/app/api/deps/auth.py` | Add get_current_tenant_id() dependency |
| `backend/app/main.py` | Add tenant_id migration hooks for users table + create Tenant #1 |
| `frontend/src/lib/store.ts` | Add tenant info to User interface |
| `frontend/src/lib/api.ts` | Add signup, verify, resendVerification to authApi |
| `frontend/src/app/login/page.tsx` | Add link to signup page, add verified=true query param handling |
| `frontend/src/app/dashboard/layout.tsx` | Show tenant name in sidebar |

---

### Task 1: Enhance Tenant Model

**Files:**
- Modify: `backend/app/db/models/tenant.py`
- Test: `backend/tests/unit/test_tenant_service.py`

- [ ] **Step 1: Write the test for Tenant model creation**

```python
# backend/tests/unit/test_tenant_service.py
"""Tests for tenant service."""
import pytest
from app.db.models.tenant import Tenant, TenantPlan


class TestTenantModel:
    """Test Tenant model and TenantPlan enum."""

    def test_tenant_plan_enum_values(self):
        assert TenantPlan.STARTER == "starter"
        assert TenantPlan.PROFESSIONAL == "professional"
        assert TenantPlan.ENTERPRISE == "enterprise"

    def test_create_tenant(self, db_session):
        tenant = Tenant(
            name="Test Corp",
            slug="test-corp",
            plan=TenantPlan.STARTER,
        )
        db_session.add(tenant)
        db_session.commit()
        db_session.refresh(tenant)

        assert tenant.tenant_id is not None
        assert tenant.name == "Test Corp"
        assert tenant.slug == "test-corp"
        assert tenant.plan == TenantPlan.STARTER
        assert tenant.max_users == 3
        assert tenant.max_mailboxes == 0
        assert tenant.max_contacts == 0
        assert tenant.max_campaigns == 0
        assert tenant.max_leads == 0
        assert tenant.is_active is True

    def test_create_enterprise_tenant(self, db_session):
        tenant = Tenant(
            name="Enterprise Inc",
            slug="enterprise-inc",
            plan=TenantPlan.ENTERPRISE,
            max_users=999,
            max_mailboxes=999,
            max_contacts=999999,
            max_campaigns=999,
            max_leads=999999,
        )
        db_session.add(tenant)
        db_session.commit()
        db_session.refresh(tenant)

        assert tenant.plan == TenantPlan.ENTERPRISE
        assert tenant.max_users == 999

    def test_tenant_slug_unique(self, db_session):
        t1 = Tenant(name="A", slug="unique-slug", plan=TenantPlan.STARTER)
        db_session.add(t1)
        db_session.commit()

        t2 = Tenant(name="B", slug="unique-slug", plan=TenantPlan.STARTER)
        db_session.add(t2)
        with pytest.raises(Exception):  # IntegrityError
            db_session.commit()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/unit/test_tenant_service.py -v`
Expected: FAIL — `TenantPlan` does not exist yet

- [ ] **Step 3: Update Tenant model**

Replace the entire contents of `backend/app/db/models/tenant.py`:

```python
"""Multi-tenant model for organization isolation."""
from enum import Enum as PyEnum
from sqlalchemy import (
    Column, Integer, String, Text, Boolean, Enum,
)
from app.db.base import Base


class TenantPlan(str, PyEnum):
    """Tenant subscription plans."""
    STARTER = "starter"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"


class Tenant(Base):
    """Tenant representing an organization/company."""

    __tablename__ = "tenants"

    tenant_id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    slug = Column(String(100), nullable=False, unique=True, index=True)
    domain = Column(String(255), nullable=True)
    logo_url = Column(String(500), nullable=True)
    plan = Column(
        Enum(TenantPlan, values_callable=lambda x: [e.value for e in x]),
        default=TenantPlan.STARTER,
        nullable=False,
    )
    is_active = Column(Boolean, default=True, nullable=False)
    settings_json = Column(Text, nullable=True)
    max_users = Column(Integer, default=3, nullable=False)
    max_mailboxes = Column(Integer, default=0, nullable=False)
    max_contacts = Column(Integer, default=0, nullable=False)
    max_campaigns = Column(Integer, default=0, nullable=False)
    max_leads = Column(Integer, default=0, nullable=False)

    def __repr__(self) -> str:
        return f"<Tenant(tenant_id={self.tenant_id}, slug='{self.slug}', plan='{self.plan}')>"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/unit/test_tenant_service.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/db/models/tenant.py backend/tests/unit/test_tenant_service.py
git commit -m "feat: enhance Tenant model with TenantPlan enum and plan limits"
```

---

### Task 2: Add Tenant Fields to User Model

**Files:**
- Modify: `backend/app/db/models/user.py`
- Test: `backend/tests/unit/test_tenant_service.py` (append)

- [ ] **Step 1: Write the test for User with tenant_id**

Append to `backend/tests/unit/test_tenant_service.py` (add imports at top of file alongside existing Tenant imports):

```python
from app.db.models.user import User, UserRole


class TestUserTenantRelation:
    """Test User model tenant_id field."""

    def test_create_user_with_tenant(self, db_session):
        tenant = Tenant(name="Corp", slug="corp", plan=TenantPlan.STARTER)
        db_session.add(tenant)
        db_session.commit()

        user = User(
            email="test@corp.com",
            password_hash="fakehash",
            full_name="Test User",
            role=UserRole.ADMIN,
            tenant_id=tenant.tenant_id,
            is_verified=True,
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        assert user.tenant_id == tenant.tenant_id
        assert user.is_verified is True

    def test_create_super_admin_without_tenant(self, db_session):
        """Super admin can have tenant_id=NULL (global user)."""
        user = User(
            email="sa@global.com",
            password_hash="fakehash",
            role=UserRole.SUPER_ADMIN,
            tenant_id=None,
            is_verified=True,
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        assert user.tenant_id is None
        assert user.role == UserRole.SUPER_ADMIN

    def test_user_defaults_unverified(self, db_session):
        tenant = Tenant(name="T", slug="t", plan=TenantPlan.STARTER)
        db_session.add(tenant)
        db_session.commit()

        user = User(
            email="new@t.com",
            password_hash="fakehash",
            tenant_id=tenant.tenant_id,
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        assert user.is_verified is False
        assert user.verification_token is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/unit/test_tenant_service.py::TestUserTenantRelation -v`
Expected: FAIL — User model has no `tenant_id`, `is_verified`, etc.

- [ ] **Step 3: Update User model**

Replace the entire contents of `backend/app/db/models/user.py`:

```python
"""User model with RBAC and multi-tenancy."""
from datetime import datetime
from enum import Enum as PyEnum
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Enum, ForeignKey
from sqlalchemy.orm import relationship
from app.db.base import Base


class UserRole(str, PyEnum):
    """User roles for RBAC."""
    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    OPERATOR = "operator"
    VIEWER = "viewer"


class User(Base):
    """User model for authentication, RBAC, and multi-tenancy."""

    __tablename__ = "users"

    user_id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=True)
    role = Column(
        Enum(UserRole, values_callable=lambda x: [e.value for e in x]),
        default=UserRole.VIEWER,
        nullable=False,
    )
    is_active = Column(Boolean, default=True, nullable=False)
    last_login_at = Column(DateTime, nullable=True)

    # Multi-tenancy
    tenant_id = Column(Integer, ForeignKey("tenants.tenant_id"), nullable=True, index=True)

    # Email verification
    is_verified = Column(Boolean, default=False, nullable=False)
    verification_token = Column(String(512), nullable=True)
    verification_sent_at = Column(DateTime, nullable=True)

    # Relationship
    tenant = relationship("Tenant", backref="users")

    def __repr__(self) -> str:
        return f"<User(user_id={self.user_id}, email='{self.email}', role='{self.role}', tenant_id={self.tenant_id})>"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/unit/test_tenant_service.py -v`
Expected: PASS (all 6 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/db/models/user.py backend/tests/unit/test_tenant_service.py
git commit -m "feat: add tenant_id, is_verified, verification fields to User model"
```

---

### Task 3: Update Schemas and JWT Token

**Files:**
- Modify: `backend/app/schemas/user.py`
- Create: `backend/app/schemas/tenant.py`
- Modify: `backend/app/core/security.py`
- Test: `backend/tests/unit/test_email_verification.py`

- [ ] **Step 1: Write the test for verification tokens**

```python
# backend/tests/unit/test_email_verification.py
"""Tests for email verification token generation and decoding."""
import pytest
from app.core.security import create_verification_token, decode_verification_token


class TestVerificationTokens:
    """Test verification token creation and decoding."""

    def test_create_verification_token(self):
        token = create_verification_token(user_id=42)
        assert isinstance(token, str)
        assert len(token) > 20

    def test_decode_verification_token(self):
        token = create_verification_token(user_id=42)
        payload = decode_verification_token(token)
        assert payload is not None
        assert payload["user_id"] == 42
        assert payload["purpose"] == "email_verification"

    def test_decode_expired_token(self):
        from datetime import timedelta
        token = create_verification_token(user_id=42, expires_delta=timedelta(seconds=-1))
        payload = decode_verification_token(token)
        assert payload is None

    def test_decode_invalid_token(self):
        payload = decode_verification_token("not.a.valid.token")
        assert payload is None

    def test_jwt_contains_tenant_id(self):
        from app.core.security import create_access_token, decode_access_token
        token = create_access_token(data={
            "sub": "user@test.com",
            "role": "admin",
            "tenant_id": 5,
            "plan": "professional",
        })
        payload = decode_access_token(token)
        assert payload["tenant_id"] == 5
        assert payload["plan"] == "professional"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/unit/test_email_verification.py -v`
Expected: FAIL — `create_verification_token` does not exist

- [ ] **Step 3: Update security.py with verification token functions**

Replace the entire contents of `backend/app/core/security.py`:

```python
"""Security utilities for authentication and authorization."""
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from app.core.config import settings

# Password hashing - using argon2 for better compatibility
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

# JWT settings
ALGORITHM = "HS256"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against a hash."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Generate a password hash."""
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token.

    The data dict should include:
      - sub: user email
      - role: user's role
      - tenant_id: user's tenant ID (None for super_admin)
      - plan: tenant's plan tier
    """
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> Optional[dict]:
    """Decode a JWT access token."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None


def create_verification_token(user_id: int, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT token for email verification.

    Args:
        user_id: The user ID to embed in the token.
        expires_delta: Custom expiry. Defaults to 24 hours.

    Returns:
        Signed JWT string.
    """
    if expires_delta is None:
        expires_delta = timedelta(hours=24)
    expire = datetime.utcnow() + expires_delta
    to_encode = {
        "user_id": user_id,
        "purpose": "email_verification",
        "exp": expire,
    }
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)


def decode_verification_token(token: str) -> Optional[dict]:
    """Decode and validate an email verification token.

    Returns:
        The token payload dict if valid, None if expired or invalid.
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("purpose") != "email_verification":
            return None
        return payload
    except JWTError:
        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/unit/test_email_verification.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Create tenant schema**

```python
# backend/app/schemas/tenant.py
"""Tenant schemas."""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, field_validator
import re


class TenantResponse(BaseModel):
    """Schema for tenant in API responses."""
    tenant_id: int
    name: str
    slug: str
    plan: str
    is_active: bool
    max_users: int
    max_mailboxes: int
    max_contacts: int
    max_campaigns: int
    max_leads: int
    created_at: datetime

    class Config:
        from_attributes = True


class TenantBrief(BaseModel):
    """Minimal tenant info embedded in user responses."""
    tenant_id: int
    name: str
    slug: str
    plan: str

    class Config:
        from_attributes = True


class SignupRequest(BaseModel):
    """Schema for self-service signup."""
    email: str = Field(..., description="User email address")
    password: str = Field(..., min_length=8, description="Password (min 8 chars, 1 uppercase, 1 number)")
    full_name: str = Field(..., min_length=1, max_length=255, description="Full name")
    company_name: str = Field(..., min_length=1, max_length=255, description="Company/organization name")

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one number")
        return v

    @staticmethod
    def slugify(name: str) -> str:
        """Convert company name to URL-safe slug."""
        slug = name.lower().strip()
        slug = re.sub(r'[^a-z0-9\s-]', '', slug)
        slug = re.sub(r'[\s-]+', '-', slug)
        slug = slug.strip('-')
        return slug[:100] if slug else "org"


class SignupResponse(BaseModel):
    """Response after successful signup."""
    message: str
    user_id: int


class VerifyResponse(BaseModel):
    """Response after email verification."""
    message: str
    verified: bool
```

- [ ] **Step 6: Update UserResponse schema to include tenant info**

Replace the entire contents of `backend/app/schemas/user.py`:

```python
"""User schemas."""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr
from app.db.models.user import UserRole


class UserBase(BaseModel):
    """Base user schema."""
    email: EmailStr
    full_name: Optional[str] = None
    role: UserRole = UserRole.VIEWER
    is_active: bool = True


class UserCreate(UserBase):
    """Schema for creating a user (admin-created, within tenant)."""
    password: str


class UserUpdate(BaseModel):
    """Schema for updating a user."""
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None


class TenantInfo(BaseModel):
    """Minimal tenant info in user response."""
    tenant_id: int
    name: str
    slug: str
    plan: str

    class Config:
        from_attributes = True


class UserResponse(UserBase):
    """Schema for user response."""
    user_id: int
    last_login_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    is_verified: bool = True
    tenant_id: Optional[int] = None
    tenant: Optional[TenantInfo] = None

    class Config:
        from_attributes = True


class UserLogin(BaseModel):
    """Schema for user login."""
    email: EmailStr
    password: str


class Token(BaseModel):
    """Schema for JWT token response."""
    access_token: str
    token_type: str = "bearer"
    user: UserResponse
```

- [ ] **Step 7: Commit**

```bash
git add backend/app/core/security.py backend/app/schemas/user.py backend/app/schemas/tenant.py backend/tests/unit/test_email_verification.py
git commit -m "feat: add verification tokens, tenant schema, tenant info in UserResponse"
```

---

### Task 4: Email Verification Service

**Files:**
- Create: `backend/app/services/email_verification.py`
- Test: `backend/tests/unit/test_email_verification.py` (append)

- [ ] **Step 1: Write the test for sending verification email**

Append to `backend/tests/unit/test_email_verification.py`:

```python
from unittest.mock import patch, MagicMock
from app.services.email_verification import send_verification_email, verify_user_email
from app.db.models.user import User, UserRole
from app.db.models.tenant import Tenant, TenantPlan
from app.core.security import create_verification_token


class TestEmailVerificationService:
    """Test email verification service functions."""

    def test_send_verification_email_sets_token(self, db_session):
        tenant = Tenant(name="T", slug="t", plan=TenantPlan.STARTER)
        db_session.add(tenant)
        db_session.commit()

        user = User(
            email="test@example.com",
            password_hash="hash",
            tenant_id=tenant.tenant_id,
            is_verified=False,
        )
        db_session.add(user)
        db_session.commit()

        with patch("app.services.email_verification._send_email") as mock_send:
            mock_send.return_value = True
            result = send_verification_email(user, db_session)
            assert result is True
            db_session.refresh(user)
            assert user.verification_token is not None
            assert user.verification_sent_at is not None
            mock_send.assert_called_once()

    def test_verify_user_email_success(self, db_session):
        tenant = Tenant(name="V", slug="v", plan=TenantPlan.STARTER)
        db_session.add(tenant)
        db_session.commit()

        user = User(
            email="verify@example.com",
            password_hash="hash",
            tenant_id=tenant.tenant_id,
            is_verified=False,
        )
        db_session.add(user)
        db_session.commit()

        token = create_verification_token(user_id=user.user_id)
        user.verification_token = token
        db_session.commit()

        result = verify_user_email(token, db_session)
        assert result is True
        db_session.refresh(user)
        assert user.is_verified is True
        assert user.verification_token is None

    def test_verify_user_email_invalid_token(self, db_session):
        result = verify_user_email("bad.token.here", db_session)
        assert result is False

    def test_verify_user_email_already_verified(self, db_session):
        tenant = Tenant(name="AV", slug="av", plan=TenantPlan.STARTER)
        db_session.add(tenant)
        db_session.commit()

        user = User(
            email="already@example.com",
            password_hash="hash",
            tenant_id=tenant.tenant_id,
            is_verified=True,
        )
        db_session.add(user)
        db_session.commit()

        token = create_verification_token(user_id=user.user_id)
        result = verify_user_email(token, db_session)
        assert result is True  # Idempotent — returns True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/unit/test_email_verification.py::TestEmailVerificationService -v`
Expected: FAIL — `email_verification` module does not exist

- [ ] **Step 3: Create email verification service**

```python
# backend/app/services/email_verification.py
"""Email verification service for signup flow."""
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
from sqlalchemy.orm import Session
import structlog

from app.core.config import settings
from app.core.security import create_verification_token, decode_verification_token
from app.db.models.user import User

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
        True if email sent (or SMTP not configured — auto-verify in dev), False on error.
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
        <p style="color: #999; font-size: 12px;">NeuraLeads — AI-Powered Sales Outreach Platform</p>
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
        return True  # Already verified — idempotent

    user.is_verified = True
    user.verification_token = None
    db.commit()

    logger.info("User email verified", user_id=user_id, email=user.email)
    return True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/unit/test_email_verification.py -v`
Expected: PASS (all 9 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/email_verification.py backend/tests/unit/test_email_verification.py
git commit -m "feat: add email verification service with token generation and SMTP sending"
```

---

### Task 5: Tenant Service (Create Tenant + Slug Generation)

**Files:**
- Create: `backend/app/services/tenant_service.py`
- Test: `backend/tests/unit/test_tenant_service.py` (append)

- [ ] **Step 1: Write the test for tenant creation service**

Append to `backend/tests/unit/test_tenant_service.py`:

```python
from app.services.tenant_service import create_tenant_for_signup, generate_unique_slug


class TestTenantService:
    """Test tenant service functions."""

    def test_generate_unique_slug(self, db_session):
        slug = generate_unique_slug("Acme Corporation", db_session)
        assert slug == "acme-corporation"

    def test_generate_unique_slug_dedup(self, db_session):
        t = Tenant(name="X", slug="acme-corp", plan=TenantPlan.STARTER)
        db_session.add(t)
        db_session.commit()

        slug = generate_unique_slug("Acme Corp", db_session)
        assert slug == "acme-corp-2"

    def test_generate_unique_slug_strips_special_chars(self, db_session):
        slug = generate_unique_slug("Test & Sons (LLC)", db_session)
        assert slug == "test--sons-llc"

    def test_create_tenant_for_signup(self, db_session):
        tenant = create_tenant_for_signup("My Startup Inc", db_session)
        assert tenant.tenant_id is not None
        assert tenant.name == "My Startup Inc"
        assert tenant.slug == "my-startup-inc"
        assert tenant.plan == TenantPlan.STARTER
        assert tenant.max_mailboxes == 0
        assert tenant.max_contacts == 0

    def test_create_tenant_slug_collision(self, db_session):
        t1 = create_tenant_for_signup("Cool Company", db_session)
        t2 = create_tenant_for_signup("Cool Company", db_session)
        assert t1.slug == "cool-company"
        assert t2.slug == "cool-company-2"
        assert t1.tenant_id != t2.tenant_id
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/unit/test_tenant_service.py::TestTenantService -v`
Expected: FAIL — `tenant_service` module does not exist

- [ ] **Step 3: Create tenant service**

```python
# backend/app/services/tenant_service.py
"""Tenant creation and management service."""
import re
from sqlalchemy.orm import Session
import structlog

from app.db.models.tenant import Tenant, TenantPlan

logger = structlog.get_logger()


def generate_unique_slug(company_name: str, db: Session) -> str:
    """Generate a unique slug from a company name.

    Args:
        company_name: The raw company name.
        db: Database session to check for collisions.

    Returns:
        A unique URL-safe slug string.
    """
    slug = company_name.lower().strip()
    slug = re.sub(r'[^a-z0-9\s-]', '', slug)
    slug = re.sub(r'[\s-]+', '-', slug)
    slug = slug.strip('-')[:100]
    if not slug:
        slug = "org"

    base_slug = slug
    counter = 2
    while db.query(Tenant).filter(Tenant.slug == slug).first() is not None:
        slug = f"{base_slug}-{counter}"
        counter += 1

    return slug


def create_tenant_for_signup(company_name: str, db: Session) -> Tenant:
    """Create a new starter tenant for self-service signup.

    Args:
        company_name: The company name from the signup form.
        db: Database session.

    Returns:
        The created Tenant record.
    """
    slug = generate_unique_slug(company_name, db)

    tenant = Tenant(
        name=company_name,
        slug=slug,
        plan=TenantPlan.STARTER,
        max_users=3,
        max_mailboxes=0,
        max_contacts=0,
        max_campaigns=0,
        max_leads=0,
    )
    db.add(tenant)
    db.commit()
    db.refresh(tenant)

    logger.info("Created tenant", tenant_id=tenant.tenant_id, name=company_name, slug=slug)
    return tenant
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/unit/test_tenant_service.py::TestTenantService -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/tenant_service.py backend/tests/unit/test_tenant_service.py
git commit -m "feat: add tenant service with slug generation and starter tenant creation"
```

---

### Task 6: Signup, Verify, and Resend Endpoints

**Files:**
- Modify: `backend/app/api/endpoints/auth.py`
- Test: `backend/tests/integration/test_auth_signup.py`

- [ ] **Step 1: Write the integration tests for signup flow**

```python
# backend/tests/integration/test_auth_signup.py
"""Integration tests for signup, verification, and login flow."""
import pytest
from unittest.mock import patch


class TestSignupFlow:
    """Test the full signup → verify → login flow."""

    def test_signup_success(self, client):
        with patch("app.services.email_verification._send_email") as mock_send:
            mock_send.return_value = True
            resp = client.post("/api/v1/auth/signup", json={
                "email": "new@startup.com",
                "password": "SecurePass123",
                "full_name": "Jane Doe",
                "company_name": "My Startup",
            })
        assert resp.status_code == 201
        data = resp.json()
        assert data["message"] == "Verification email sent. Check your inbox."
        assert "user_id" in data

    def test_signup_duplicate_email(self, client):
        with patch("app.services.email_verification._send_email") as mock_send:
            mock_send.return_value = True
            client.post("/api/v1/auth/signup", json={
                "email": "dup@test.com",
                "password": "SecurePass123",
                "full_name": "User One",
                "company_name": "Company A",
            })
            resp = client.post("/api/v1/auth/signup", json={
                "email": "dup@test.com",
                "password": "SecurePass123",
                "full_name": "User Two",
                "company_name": "Company B",
            })
        assert resp.status_code == 400
        assert "already registered" in resp.json()["detail"]

    def test_signup_weak_password(self, client):
        resp = client.post("/api/v1/auth/signup", json={
            "email": "weak@test.com",
            "password": "short",
            "full_name": "Weak User",
            "company_name": "Corp",
        })
        assert resp.status_code == 422  # Pydantic validation (min_length=8)

    def test_signup_missing_company_name(self, client):
        resp = client.post("/api/v1/auth/signup", json={
            "email": "nocompany@test.com",
            "password": "SecurePass123",
            "full_name": "No Company User",
        })
        assert resp.status_code == 422

    def test_verify_email_success(self, client):
        with patch("app.services.email_verification._send_email") as mock_send:
            mock_send.return_value = True
            signup_resp = client.post("/api/v1/auth/signup", json={
                "email": "verify@test.com",
                "password": "SecurePass123",
                "full_name": "Verify User",
                "company_name": "Verify Corp",
            })
        user_id = signup_resp.json()["user_id"]

        # Get the verification token from DB
        from app.db.base import SessionLocal
        from app.db.models.user import User
        db = SessionLocal()
        user = db.query(User).filter(User.user_id == user_id).first()
        token = user.verification_token
        db.close()

        resp = client.get(f"/api/v1/auth/verify?token={token}")
        assert resp.status_code == 200
        assert resp.json()["verified"] is True

    def test_verify_invalid_token(self, client):
        resp = client.get("/api/v1/auth/verify?token=invalid.token.here")
        assert resp.status_code == 400

    def test_login_unverified_user_blocked(self, client):
        with patch("app.services.email_verification._send_email") as mock_send:
            mock_send.return_value = True
            client.post("/api/v1/auth/signup", json={
                "email": "unverified@test.com",
                "password": "SecurePass123",
                "full_name": "Unverified",
                "company_name": "UV Corp",
            })
        # Try to login without verifying
        resp = client.post("/api/v1/auth/login", data={
            "username": "unverified@test.com",
            "password": "SecurePass123",
        })
        assert resp.status_code == 403
        assert "not verified" in resp.json()["detail"].lower()

    def test_login_after_verification(self, client):
        with patch("app.services.email_verification._send_email") as mock_send:
            mock_send.return_value = True
            signup_resp = client.post("/api/v1/auth/signup", json={
                "email": "verified@test.com",
                "password": "SecurePass123",
                "full_name": "Verified User",
                "company_name": "V Corp",
            })
        user_id = signup_resp.json()["user_id"]

        # Verify
        from app.db.base import SessionLocal
        from app.db.models.user import User
        db = SessionLocal()
        user = db.query(User).filter(User.user_id == user_id).first()
        token = user.verification_token
        db.close()
        client.get(f"/api/v1/auth/verify?token={token}")

        # Login
        resp = client.post("/api/v1/auth/login", data={
            "username": "verified@test.com",
            "password": "SecurePass123",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["user"]["tenant_id"] is not None
        assert data["user"]["tenant"]["plan"] == "starter"

    def test_register_endpoint_requires_auth(self, client):
        """Old /register endpoint should require authentication now."""
        resp = client.post("/api/v1/auth/register", json={
            "email": "admin-created@test.com",
            "password": "SecurePass123",
            "full_name": "Admin Created",
        })
        assert resp.status_code == 401

    def test_register_endpoint_no_role_injection(self, client, admin_token):
        """Verify role from request body is ignored — always viewer."""
        resp = client.post(
            "/api/v1/auth/register",
            json={
                "email": "tryrole@test.com",
                "password": "SecurePass123",
                "full_name": "Role Injector",
                "role": "admin",
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["role"] == "viewer"


class TestResendVerification:
    """Test resend verification endpoint."""

    def test_resend_success(self, client):
        with patch("app.services.email_verification._send_email") as mock_send:
            mock_send.return_value = True
            client.post("/api/v1/auth/signup", json={
                "email": "resend@test.com",
                "password": "SecurePass123",
                "full_name": "Resend User",
                "company_name": "Resend Corp",
            })
            resp = client.post("/api/v1/auth/resend-verification", json={
                "email": "resend@test.com",
            })
        assert resp.status_code == 200
        assert "sent" in resp.json()["message"].lower()

    def test_resend_nonexistent_email(self, client):
        resp = client.post("/api/v1/auth/resend-verification", json={
            "email": "ghost@nowhere.com",
        })
        # Should return 200 to prevent email enumeration
        assert resp.status_code == 200
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/integration/test_auth_signup.py -v`
Expected: FAIL — `/auth/signup` endpoint does not exist

- [ ] **Step 3: Rewrite auth.py with signup, verify, resend endpoints + fix register**

Replace the entire contents of `backend/app/api/endpoints/auth.py`:

```python
"""Authentication endpoints."""
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.api.deps import get_db, get_current_active_user
from app.core.security import verify_password, get_password_hash, create_access_token
from app.core.config import settings
from app.db.models.user import User, UserRole
from app.schemas.user import UserCreate, UserResponse, Token
from app.schemas.tenant import SignupRequest, SignupResponse, VerifyResponse

limiter = Limiter(key_func=get_remote_address, swallow_errors=True)
router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login", response_model=Token)
@limiter.limit("5/minute")
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    """Authenticate user and return JWT token."""
    user = db.query(User).filter(User.email == form_data.username).first()

    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user account"
        )

    # Check email verification (skip for pre-existing users without tenant)
    if not user.is_verified and user.tenant_id is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email not verified. Check your inbox for the verification link."
        )

    # Update last login
    user.last_login_at = datetime.utcnow()
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

    # Check if email exists
    existing_user = db.query(User).filter(User.email == user_in.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    # SECURITY FIX: Ignore role from request body — always create as viewer
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
```

- [ ] **Step 4: Run integration tests**

Run: `cd backend && python -m pytest tests/integration/test_auth_signup.py -v`
Expected: Most tests PASS. Some may need fixture adjustments (admin_token).

- [ ] **Step 5: Run full test suite to check for regressions**

Run: `cd backend && python -m pytest -x --timeout=60`
Expected: Existing tests may need minor fixes for the new is_verified field and register requiring auth.

- [ ] **Step 6: Fix any test regressions**

Likely fixes needed in existing test fixtures:
- Add `is_verified=True` when creating test users
- Add `tenant_id` to test users (create a test tenant in conftest)
- Update register tests to pass auth token

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/endpoints/auth.py backend/tests/integration/test_auth_signup.py
git commit -m "feat: add signup/verify/resend endpoints, fix role injection in register"
```

---

### Task 7: Tenant-Aware Auth Dependency

**Files:**
- Modify: `backend/app/api/deps/auth.py`
- Test: `backend/tests/unit/test_email_verification.py` (append)

- [ ] **Step 1: Write the test for get_current_tenant_id**

Append to `backend/tests/unit/test_email_verification.py`:

```python
class TestTenantDependency:
    """Test the tenant_id extraction dependency."""

    def test_tenant_id_from_regular_user(self, db_session):
        from app.db.models.tenant import Tenant, TenantPlan
        from app.api.deps.auth import _extract_tenant_id

        tenant = Tenant(name="Dep", slug="dep", plan=TenantPlan.PROFESSIONAL)
        db_session.add(tenant)
        db_session.commit()

        user = User(
            email="dep@test.com", password_hash="h", tenant_id=tenant.tenant_id,
            is_verified=True, role=UserRole.ADMIN,
        )
        db_session.add(user)
        db_session.commit()

        tid = _extract_tenant_id(user, x_tenant_id=None)
        assert tid == tenant.tenant_id

    def test_tenant_id_none_for_super_admin(self, db_session):
        from app.api.deps.auth import _extract_tenant_id

        sa = User(
            email="sa@test.com", password_hash="h", tenant_id=None,
            is_verified=True, role=UserRole.SUPER_ADMIN,
        )
        db_session.add(sa)
        db_session.commit()

        tid = _extract_tenant_id(sa, x_tenant_id=None)
        assert tid is None

    def test_super_admin_can_impersonate_tenant(self, db_session):
        from app.db.models.tenant import Tenant, TenantPlan
        from app.api.deps.auth import _extract_tenant_id

        tenant = Tenant(name="Imp", slug="imp", plan=TenantPlan.STARTER)
        db_session.add(tenant)
        db_session.commit()

        sa = User(
            email="sa2@test.com", password_hash="h", tenant_id=None,
            is_verified=True, role=UserRole.SUPER_ADMIN,
        )
        db_session.add(sa)
        db_session.commit()

        tid = _extract_tenant_id(sa, x_tenant_id=tenant.tenant_id)
        assert tid == tenant.tenant_id

    def test_regular_user_cannot_impersonate(self, db_session):
        from app.db.models.tenant import Tenant, TenantPlan
        from app.api.deps.auth import _extract_tenant_id

        tenant = Tenant(name="No", slug="no", plan=TenantPlan.STARTER)
        db_session.add(tenant)
        db_session.commit()

        user = User(
            email="noimper@test.com", password_hash="h",
            tenant_id=tenant.tenant_id, is_verified=True, role=UserRole.ADMIN,
        )
        db_session.add(user)
        db_session.commit()

        # Even if X-Tenant-ID is passed, regular user's own tenant_id is returned
        tid = _extract_tenant_id(user, x_tenant_id=999)
        assert tid == tenant.tenant_id
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/unit/test_email_verification.py::TestTenantDependency -v`
Expected: FAIL — `_extract_tenant_id` does not exist

- [ ] **Step 3: Add tenant dependency to auth.py**

Add the following to the **end** of `backend/app/api/deps/auth.py` (after the existing `get_all_settings_tab_permissions` function):

```python
from typing import Optional as _Optional
from fastapi import Header as _Header


def _extract_tenant_id(user: User, x_tenant_id: _Optional[int] = None) -> _Optional[int]:
    """Extract tenant_id from user context.

    - Super admin: returns None (all-tenant access) unless X-Tenant-ID header is set.
    - Regular user: always returns their own tenant_id (ignores header).

    Args:
        user: The authenticated User.
        x_tenant_id: Optional tenant ID from X-Tenant-ID header (super admin only).

    Returns:
        The tenant_id to scope queries to, or None for super admin global access.
    """
    if user.role == UserRole.SUPER_ADMIN:
        return x_tenant_id  # None = global, or specific tenant for impersonation
    return user.tenant_id


async def get_current_tenant_id(
    current_user: User = Depends(get_current_active_user),
    x_tenant_id: _Optional[int] = _Header(None, alias="X-Tenant-ID"),
) -> _Optional[int]:
    """Dependency: get the tenant_id for scoping queries.

    - Super admin without X-Tenant-ID: returns None (sees all tenants).
    - Super admin with X-Tenant-ID: returns that tenant_id (impersonation).
    - Regular user: returns their tenant_id (always).
    - User without tenant: raises 403.
    """
    tid = _extract_tenant_id(current_user, x_tenant_id)
    if tid is None and current_user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tenant assigned to this user",
        )
    return tid
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/unit/test_email_verification.py::TestTenantDependency -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/deps/auth.py backend/tests/unit/test_email_verification.py
git commit -m "feat: add get_current_tenant_id dependency for tenant-scoped queries"
```

---

### Task 8: Database Migration — Add tenant_id to Users + Create Tenant #1

**Files:**
- Modify: `backend/app/main.py` (add migration hooks)

- [ ] **Step 1: Add migration block to main.py lifespan**

Add the following migration block inside the `lifespan()` function in `backend/app/main.py`, **after the existing migration blocks** (after the last `try/except` migration block, before `_seed_warmup_profiles()` or `_seed_deal_stages()` calls):

```python
    # Migration: Multi-tenancy — add tenant_id + verification columns to users
    try:
        from sqlalchemy import text as sa_text_mt, inspect as sa_inspect_mt
        with engine.connect() as conn:
            inspector_mt = sa_inspect_mt(engine)

            # 1. Ensure tenants table exists (created by SQLAlchemy, but verify plan column type)
            if "tenants" in inspector_mt.get_table_names():
                tenant_cols = [c["name"] for c in inspector_mt.get_columns("tenants")]
                # Add new columns if migrating from old tenant model
                for col_name, col_def in [
                    ("max_users", "INT DEFAULT 3 NOT NULL"),
                    ("max_leads", "INT DEFAULT 0 NOT NULL"),
                ]:
                    if col_name not in tenant_cols:
                        try:
                            conn.execute(sa_text_mt(f"ALTER TABLE tenants ADD COLUMN {col_name} {col_def}"))
                            conn.commit()
                            logger.info(f"Migration: added {col_name} to tenants")
                        except Exception:
                            pass

            # 2. Add tenant_id to users if missing
            user_cols = [c["name"] for c in inspector_mt.get_columns("users")]
            for col_name, col_def in [
                ("tenant_id", "INT NULL"),
                ("is_verified", "BOOLEAN DEFAULT 1 NOT NULL"),
                ("verification_token", "VARCHAR(512) NULL"),
                ("verification_sent_at", "DATETIME NULL"),
            ]:
                if col_name not in user_cols:
                    try:
                        conn.execute(sa_text_mt(f"ALTER TABLE users ADD COLUMN {col_name} {col_def}"))
                        conn.commit()
                        logger.info(f"Migration: added {col_name} to users")
                    except Exception:
                        pass

            # 3. Create Tenant #1 (primary tenant) if not exists
            try:
                result = conn.execute(sa_text_mt("SELECT tenant_id FROM tenants WHERE tenant_id = 1"))
                if result.fetchone() is None:
                    conn.execute(sa_text_mt(
                        "INSERT INTO tenants (tenant_id, name, slug, plan, is_active, max_users, max_mailboxes, max_contacts, max_campaigns, max_leads, created_at, updated_at, is_archived) "
                        "VALUES (1, 'Exzelon', 'exzelon', 'enterprise', 1, 999, 999, 999999, 999, 999999, NOW(), NOW(), 0)"
                    ))
                    conn.commit()
                    logger.info("Migration: created primary Tenant #1 (Exzelon)")
            except Exception as e3:
                logger.debug(f"Tenant #1 creation (may already exist): {e3}")

            # 4. Assign all existing users to Tenant #1 (except super_admin)
            try:
                conn.execute(sa_text_mt(
                    "UPDATE users SET tenant_id = 1 WHERE tenant_id IS NULL AND role != 'super_admin'"
                ))
                conn.commit()
                logger.info("Migration: assigned existing users to Tenant #1")
            except Exception as e4:
                logger.debug(f"User tenant assignment: {e4}")

            # 5. Mark all existing users as verified
            try:
                conn.execute(sa_text_mt(
                    "UPDATE users SET is_verified = 1 WHERE is_verified = 0 OR is_verified IS NULL"
                ))
                conn.commit()
                logger.info("Migration: marked existing users as verified")
            except Exception as e5:
                logger.debug(f"User verification backfill: {e5}")

    except Exception as e:
        logger.warning(f"Migration check for multi-tenancy: {e}")
```

- [ ] **Step 2: Test migration locally**

Run: `cd backend && uvicorn app.main:app --reload --port 8000`
Check logs for: "Migration: created primary Tenant #1" and "assigned existing users to Tenant #1"

Verify in MySQL:
```bash
cd backend && python -c "
from app.db.base import SessionLocal
from app.db.models.tenant import Tenant
from app.db.models.user import User
db = SessionLocal()
t = db.query(Tenant).filter(Tenant.tenant_id == 1).first()
print(f'Tenant: {t.name}, plan={t.plan}')
users = db.query(User).all()
for u in users:
    print(f'  User: {u.email}, tenant_id={u.tenant_id}, verified={u.is_verified}')
db.close()
"
```

Expected: Tenant #1 exists as "Exzelon" with enterprise plan. All non-SA users have tenant_id=1.

- [ ] **Step 3: Commit**

```bash
git add backend/app/main.py
git commit -m "feat: add multi-tenancy migration — tenant_id on users, create Tenant #1, backfill existing data"
```

---

### Task 9: Frontend — Signup Page

**Files:**
- Create: `frontend/src/app/signup/page.tsx`
- Create: `frontend/src/app/verify/page.tsx`
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/lib/store.ts`
- Modify: `frontend/src/app/login/page.tsx`

- [ ] **Step 1: Add signup and verify to API client**

Add after `authApi.me` (at line ~85) in `frontend/src/lib/api.ts`:

```typescript
  signup: async (data: { email: string; password: string; full_name: string; company_name: string }) => {
    const response = await api.post('/auth/signup', data)
    return response.data
  },
  verify: async (token: string) => {
    const response = await api.get('/auth/verify', { params: { token } })
    return response.data
  },
  resendVerification: async (email: string) => {
    const response = await api.post('/auth/resend-verification', { email })
    return response.data
  },
```

- [ ] **Step 2: Update User interface in store.ts**

Replace the `User` interface in `frontend/src/lib/store.ts` (lines 4-10):

```typescript
interface Tenant {
  tenant_id: number
  name: string
  slug: string
  plan: string
}

interface User {
  user_id: number
  email: string
  full_name: string | null
  role: 'super_admin' | 'admin' | 'operator' | 'viewer'
  is_active: boolean
  tenant_id: number | null
  tenant: Tenant | null
  is_verified: boolean
}
```

- [ ] **Step 3: Create signup page**

```tsx
// frontend/src/app/signup/page.tsx
'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { authApi } from '@/lib/api'
import { Brain, Building, Mail, User, Lock, ArrowRight, CheckCircle } from 'lucide-react'

export default function SignupPage() {
  const router = useRouter()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState(false)
  const [formData, setFormData] = useState({
    full_name: '',
    company_name: '',
    email: '',
    password: '',
  })

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)

    try {
      await authApi.signup(formData)
      setSuccess(true)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'An error occurred. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  if (success) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-primary-50 to-primary-100">
        <div className="w-full max-w-md">
          <div className="card text-center">
            <div className="w-16 h-16 bg-green-100 rounded-full flex items-center justify-center mx-auto mb-4">
              <CheckCircle className="w-8 h-8 text-green-600" />
            </div>
            <h2 className="text-2xl font-bold text-gray-800 mb-2">Check your email</h2>
            <p className="text-gray-600 mb-6">
              We sent a verification link to <strong>{formData.email}</strong>.
              Click the link to activate your account.
            </p>
            <p className="text-sm text-gray-500 mb-4">
              Didn&apos;t receive the email? Check your spam folder or{' '}
              <button
                onClick={async () => {
                  try {
                    await authApi.resendVerification(formData.email)
                    setError('')
                  } catch {
                    setError('Failed to resend. Please try again later.')
                  }
                }}
                className="text-primary-600 hover:underline"
              >
                resend it
              </button>.
            </p>
            <Link href="/login" className="text-primary-600 hover:text-primary-700 text-sm">
              Back to Sign In
            </Link>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-primary-50 to-primary-100">
      <div className="w-full max-w-md">
        <div className="card">
          <div className="text-center mb-8">
            <div className="flex items-center justify-center gap-2 mb-3">
              <div className="w-10 h-10 bg-gradient-to-br from-primary-500 to-primary-700 rounded-xl flex items-center justify-center shadow-lg">
                <Brain className="w-6 h-6 text-white" />
              </div>
            </div>
            <h1 className="text-2xl font-bold text-gray-800">Get Started Free</h1>
            <p className="text-gray-500 mt-2 text-sm">Create your NeuraLeads account</p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="label">Full Name</label>
              <div className="relative">
                <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                <input
                  type="text"
                  className="input pl-10"
                  value={formData.full_name}
                  onChange={(e) => setFormData({ ...formData, full_name: e.target.value })}
                  placeholder="John Doe"
                  required
                />
              </div>
            </div>

            <div>
              <label className="label">Company Name</label>
              <div className="relative">
                <Building className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                <input
                  type="text"
                  className="input pl-10"
                  value={formData.company_name}
                  onChange={(e) => setFormData({ ...formData, company_name: e.target.value })}
                  placeholder="Acme Inc"
                  required
                />
              </div>
            </div>

            <div>
              <label className="label">Work Email</label>
              <div className="relative">
                <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                <input
                  type="email"
                  className="input pl-10"
                  value={formData.email}
                  onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                  placeholder="you@company.com"
                  required
                />
              </div>
            </div>

            <div>
              <label className="label">Password</label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                <input
                  type="password"
                  className="input pl-10"
                  value={formData.password}
                  onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                  placeholder="Min 8 characters"
                  required
                  minLength={8}
                />
              </div>
            </div>

            {error && (
              <div className="bg-red-50 text-red-600 px-4 py-2 rounded-lg text-sm">{error}</div>
            )}

            <button type="submit" className="btn-primary w-full" disabled={loading}>
              {loading ? 'Creating account...' : 'Create Account'}
            </button>
          </form>

          <div className="mt-6 text-center">
            <Link href="/login" className="text-primary-600 hover:text-primary-700 text-sm">
              Already have an account? Sign in
            </Link>
          </div>
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Create verification page**

```tsx
// frontend/src/app/verify/page.tsx
'use client'

import { useEffect, useState, Suspense } from 'react'
import { useSearchParams } from 'next/navigation'
import Link from 'next/link'
import { authApi } from '@/lib/api'
import { CheckCircle, XCircle, Loader2 } from 'lucide-react'

function VerifyContent() {
  const searchParams = useSearchParams()
  const token = searchParams.get('token')
  const [status, setStatus] = useState<'loading' | 'success' | 'error'>('loading')
  const [message, setMessage] = useState('')

  useEffect(() => {
    if (!token) {
      setStatus('error')
      setMessage('No verification token provided.')
      return
    }

    authApi.verify(token)
      .then(() => {
        setStatus('success')
        setMessage('Your email has been verified!')
      })
      .catch((err) => {
        setStatus('error')
        setMessage(err.response?.data?.detail || 'Verification failed. The link may have expired.')
      })
  }, [token])

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-primary-50 to-primary-100">
      <div className="w-full max-w-md">
        <div className="card text-center">
          {status === 'loading' && (
            <>
              <Loader2 className="w-12 h-12 text-primary-500 animate-spin mx-auto mb-4" />
              <h2 className="text-xl font-bold text-gray-800">Verifying your email...</h2>
            </>
          )}
          {status === 'success' && (
            <>
              <div className="w-16 h-16 bg-green-100 rounded-full flex items-center justify-center mx-auto mb-4">
                <CheckCircle className="w-8 h-8 text-green-600" />
              </div>
              <h2 className="text-2xl font-bold text-gray-800 mb-2">{message}</h2>
              <p className="text-gray-600 mb-6">You can now sign in to your account.</p>
              <Link href="/login?verified=true" className="btn-primary inline-block px-6 py-2">
                Sign In
              </Link>
            </>
          )}
          {status === 'error' && (
            <>
              <div className="w-16 h-16 bg-red-100 rounded-full flex items-center justify-center mx-auto mb-4">
                <XCircle className="w-8 h-8 text-red-600" />
              </div>
              <h2 className="text-2xl font-bold text-gray-800 mb-2">Verification Failed</h2>
              <p className="text-gray-600 mb-6">{message}</p>
              <Link href="/login" className="text-primary-600 hover:text-primary-700">
                Back to Sign In
              </Link>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

export default function VerifyPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-primary-500" />
      </div>
    }>
      <VerifyContent />
    </Suspense>
  )
}
```

- [ ] **Step 5: Update login page — remove inline signup, add link to /signup**

Replace the entire contents of `frontend/src/app/login/page.tsx`:

```tsx
'use client'

import { useState, useEffect, Suspense } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import Link from 'next/link'
import { useAuthStore } from '@/lib/store'
import { authApi } from '@/lib/api'
import { Brain, ArrowRight, CheckCircle } from 'lucide-react'

function LoginContent() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const { setAuth } = useAuthStore()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [verified, setVerified] = useState(false)

  const [formData, setFormData] = useState({
    email: '',
    password: '',
  })

  useEffect(() => {
    if (searchParams.get('verified') === 'true') {
      setVerified(true)
    }
  }, [searchParams])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)

    try {
      const response = await authApi.login(formData.email, formData.password)
      setAuth(response.access_token, response.user)
      router.push('/dashboard')
    } catch (err: any) {
      setError(err.response?.data?.detail || 'An error occurred')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-primary-50 to-primary-100">
      <div className="w-full max-w-md">
        <div className="card">
          <div className="text-center mb-8">
            <div className="flex items-center justify-center gap-2 mb-3">
              <div className="w-10 h-10 bg-gradient-to-br from-primary-500 to-primary-700 rounded-xl flex items-center justify-center shadow-lg">
                <Brain className="w-6 h-6 text-white" />
              </div>
            </div>
            <h1 className="text-3xl font-bold text-gray-800 flex items-center justify-center gap-2">
              <span className="bg-gradient-to-r from-primary-600 to-primary-500 bg-clip-text text-transparent">NeuraMail</span>
              <ArrowRight className="w-5 h-5 text-gray-400" />
              <span className="bg-gradient-to-r from-primary-500 to-emerald-500 bg-clip-text text-transparent">NeuraLeads</span>
            </h1>
            <p className="text-gray-500 mt-2 text-sm">AI-Powered Cold Email & Lead Generation</p>
          </div>

          {verified && (
            <div className="bg-green-50 text-green-700 px-4 py-3 rounded-lg text-sm mb-4 flex items-center gap-2">
              <CheckCircle className="w-4 h-4 flex-shrink-0" />
              Email verified successfully! You can now sign in.
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="label">Email</label>
              <input
                type="email"
                className="input"
                value={formData.email}
                onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                placeholder="you@example.com"
                required
              />
            </div>

            <div>
              <label className="label">Password</label>
              <input
                type="password"
                className="input"
                value={formData.password}
                onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                placeholder="Enter password"
                required
              />
            </div>

            {error && (
              <div className="bg-red-50 text-red-600 px-4 py-2 rounded-lg text-sm">{error}</div>
            )}

            <button type="submit" className="btn-primary w-full" disabled={loading}>
              {loading ? 'Please wait...' : 'Sign In'}
            </button>
          </form>

          <div className="mt-6 text-center">
            <Link href="/signup" className="text-primary-600 hover:text-primary-700 text-sm">
              Don&apos;t have an account? Get Started Free
            </Link>
          </div>
        </div>
      </div>
    </div>
  )
}

export default function LoginPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-primary-50 to-primary-100">
        <div className="text-gray-500">Loading...</div>
      </div>
    }>
      <LoginContent />
    </Suspense>
  )
}
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/signup/page.tsx frontend/src/app/verify/page.tsx frontend/src/app/login/page.tsx frontend/src/lib/api.ts frontend/src/lib/store.ts
git commit -m "feat: add signup page with company name, email verification page, and update login flow"
```

---

### Task 10: Show Tenant Name in Sidebar

**Files:**
- Modify: `frontend/src/app/dashboard/layout.tsx`

- [ ] **Step 1: Update sidebar header to show tenant name**

In `frontend/src/app/dashboard/layout.tsx`, replace lines 143-157 (the sidebar header `<div className="p-4 border-b border-gray-700">` block):

```tsx
      <div className="p-4 border-b border-gray-700">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold">NeuraLeads</h1>
            <p className="text-gray-400 text-sm mt-1 truncate">
              {user?.tenant?.name || 'Admin Panel'}
            </p>
          </div>
          <button
            onClick={() => setSidebarOpen(false)}
            className="lg:hidden text-gray-400 hover:text-white"
            aria-label="Close sidebar"
          >
            <X className="w-5 h-5" />
          </button>
        </div>
      </div>
```

- [ ] **Step 2: Verify locally**

Open http://localhost:3000/dashboard — sidebar should show "NeuraLeads" with tenant name below it.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/dashboard/layout.tsx
git commit -m "feat: show tenant name in dashboard sidebar header"
```

---

### Task 11: Run Full Test Suite and Fix Regressions

**Files:**
- Modify: `backend/tests/conftest.py` (if needed)
- Various test files for fixture updates

- [ ] **Step 1: Run backend tests**

Run: `cd backend && python -m pytest --timeout=60 -x -v 2>&1 | head -80`
Note any failures related to: missing tenant_id, is_verified defaults, register requiring auth.

- [ ] **Step 2: Fix conftest.py test fixtures**

The test fixtures that create users need to set `is_verified=True` and `tenant_id`. Update `backend/tests/conftest.py`:

Find the fixture that creates test users and add:
```python
# After creating the test user, set tenant fields
user.tenant_id = test_tenant.tenant_id  # Create a test tenant fixture
user.is_verified = True
```

Create a `test_tenant` fixture:
```python
@pytest.fixture
def test_tenant(db_session):
    from app.db.models.tenant import Tenant, TenantPlan
    tenant = Tenant(name="Test Org", slug="test-org", plan=TenantPlan.ENTERPRISE, max_users=999, max_mailboxes=999, max_contacts=999999, max_campaigns=999, max_leads=999999)
    db_session.add(tenant)
    db_session.commit()
    return tenant
```

- [ ] **Step 3: Run full test suite again**

Run: `cd backend && python -m pytest --timeout=60 -v`
Expected: All tests pass

- [ ] **Step 4: Run frontend build**

Run: `cd frontend && npm run build`
Expected: Build succeeds with no TypeScript errors

- [ ] **Step 5: Commit any fixes**

```bash
git add -A
git commit -m "fix: update test fixtures for multi-tenancy fields (tenant_id, is_verified)"
```

---

### Task 12: Update Plan_WIP.md and CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`
- Modify: `Plan_WIP.md`

- [ ] **Step 1: Update CLAUDE.md with multi-tenancy info**

Add to the "Key Data Models" section:
```markdown
- **Tenant** -- organization/company with plan tier (starter/professional/enterprise), limits, and data isolation scope
```

Add to the "Auth" section:
```markdown
JWT tokens now include `tenant_id` and `plan`. New signup flow: POST /auth/signup creates Tenant + User, sends verification email. Email must be verified before login. The /auth/register endpoint now requires authentication (admin use only) and always creates viewer role (fixes role injection vulnerability).
```

- [ ] **Step 2: Update Plan_WIP.md**

```markdown
## SESSION_CONTEXT_RETRIEVAL
> Phase 1 of multi-tenancy complete: Tenant model, User model (tenant_id, is_verified), email verification, signup/verify/resend endpoints, tenant-aware JWT, get_current_tenant_id dependency, frontend signup/verify pages, login page update, sidebar tenant name. Migration backfills existing data to Tenant #1. Next: Phase 2 — add tenant_id to core data tables (leads, contacts, clients, mailboxes) and retrofit their endpoints.
```

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md Plan_WIP.md
git commit -m "docs: update CLAUDE.md and Plan_WIP.md for Phase 1 multi-tenancy completion"
```

---

## Summary: What Phase 1 Delivers

After completing all 12 tasks:

1. **Tenant model** activated with plan tiers (starter/professional/enterprise)
2. **User model** now has tenant_id, is_verified, verification_token fields
3. **Email-verified signup** via POST /auth/signup with mandatory company name
4. **Verification flow** with JWT-signed email links (24h expiry)
5. **JWT tokens** contain tenant_id and plan
6. **get_current_tenant_id()** dependency ready for all endpoint retrofitting
7. **Role injection fixed** — /register requires auth, always creates viewer
8. **Existing data migrated** to Tenant #1 (Exzelon, enterprise plan)
9. **Frontend** has dedicated /signup page, /verify page, updated /login page
10. **Sidebar** shows tenant (company) name

## What Comes Next (Phase 2)

Phase 2 adds `tenant_id` to the 4 core data tables (leads, contacts, clients, mailboxes) and retrofits all their endpoints (~56 routes) to filter by tenant_id. This is where actual data isolation begins.
