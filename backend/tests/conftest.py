"""Pytest configuration and fixtures."""
import os
import pytest
from datetime import date, datetime
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import StaticPool

# Set test database URL BEFORE importing app to avoid MySQL connection
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["DEBUG"] = "False"
os.environ.setdefault("ENCRYPTION_KEY", "kbt_mh7zLmsYjFAGgX_MAVtAousWEe7CQUtbNsi9m44=")
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")

from app.main import app
from app.db.base import Base
from app.api.deps.database import get_db
from app.core.security import get_password_hash, create_access_token
from app.db.models.user import User, UserRole
from app.db.models.tenant import Tenant, TenantPlan
from app.db.models.lead import LeadDetails, LeadStatus
from app.db.models.email_template import EmailTemplate, TemplateStatus
from app.db.models.sender_mailbox import SenderMailbox, WarmupStatus
from app.db.models.warmup_profile import WarmupProfile
from app.db.models.job_run import JobRun, JobStatus

# Use SQLite for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    """Override database dependency for testing."""
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


@pytest.fixture(scope="function")
def db_session():
    """Create a fresh database session for each test."""
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(db_session):
    """Create a test client with database override."""
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Tenant fixture (shared by all user fixtures)
# ---------------------------------------------------------------------------

@pytest.fixture
def test_tenant(db_session):
    """Create a test tenant for testing."""
    tenant = Tenant(
        name="Test Org",
        slug="test-org",
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
    return tenant


# ---------------------------------------------------------------------------
# User fixtures (all with tenant_id and is_verified)
# ---------------------------------------------------------------------------

@pytest.fixture
def super_admin_user(db_session):
    """Create a super admin user for testing (global, no tenant)."""
    user = User(
        email="superadmin@test.com",
        password_hash=get_password_hash("testpassword"),
        full_name="Super Admin User",
        role=UserRole.SUPER_ADMIN,
        is_active=True,
        is_verified=True,
        tenant_id=None,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def admin_user(db_session, test_tenant):
    """Create an admin user for testing."""
    user = User(
        email="admin@test.com",
        password_hash=get_password_hash("testpassword"),
        full_name="Admin User",
        role=UserRole.ADMIN,
        is_active=True,
        is_verified=True,
        tenant_id=test_tenant.tenant_id,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def operator_user(db_session, test_tenant):
    """Create an operator user for testing."""
    user = User(
        email="operator@test.com",
        password_hash=get_password_hash("testpassword"),
        full_name="Operator User",
        role=UserRole.OPERATOR,
        is_active=True,
        is_verified=True,
        tenant_id=test_tenant.tenant_id,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def viewer_user(db_session, test_tenant):
    """Create a viewer user for testing."""
    user = User(
        email="viewer@test.com",
        password_hash=get_password_hash("testpassword"),
        full_name="Viewer User",
        role=UserRole.VIEWER,
        is_active=True,
        is_verified=True,
        tenant_id=test_tenant.tenant_id,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


# ---------------------------------------------------------------------------
# Token fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def super_admin_token(super_admin_user):
    """Create a super admin JWT token."""
    return create_access_token(data={
        "sub": super_admin_user.email,
        "role": super_admin_user.role.value,
        "tenant_id": None,
        "plan": None,
    })


@pytest.fixture
def admin_token(admin_user):
    """Create an admin JWT token."""
    return create_access_token(data={
        "sub": admin_user.email,
        "role": admin_user.role.value,
        "tenant_id": admin_user.tenant_id,
        "plan": "enterprise",
    })


@pytest.fixture
def operator_token(operator_user):
    """Create an operator JWT token."""
    return create_access_token(data={
        "sub": operator_user.email,
        "role": operator_user.role.value,
        "tenant_id": operator_user.tenant_id,
        "plan": "enterprise",
    })


@pytest.fixture
def viewer_token(viewer_user):
    """Create a viewer JWT token."""
    return create_access_token(data={
        "sub": viewer_user.email,
        "role": viewer_user.role.value,
        "tenant_id": viewer_user.tenant_id,
        "plan": "enterprise",
    })


@pytest.fixture
def sa_headers(super_admin_token):
    """Create authorization headers with super admin token."""
    return {"Authorization": f"Bearer {super_admin_token}"}


@pytest.fixture
def auth_headers(admin_token):
    """Create authorization headers with admin token."""
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture
def operator_headers(operator_token):
    """Create authorization headers with operator token."""
    return {"Authorization": f"Bearer {operator_token}"}


@pytest.fixture
def viewer_headers(viewer_token):
    """Create authorization headers with viewer token."""
    return {"Authorization": f"Bearer {viewer_token}"}


# ---------------------------------------------------------------------------
# Shared domain fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_lead(db_session, test_tenant):
    """Create a sample lead for testing."""
    lead = LeadDetails(
        tenant_id=test_tenant.tenant_id,
        client_name="Fixture Corp",
        job_title="Software Engineer",
        state="TX",
        posting_date=date.today(),
        job_link="https://jobs.example.com/fixture-1",
        salary_min=60000,
        salary_max=90000,
        source="linkedin",
        lead_status=LeadStatus.NEW,
    )
    db_session.add(lead)
    db_session.commit()
    db_session.refresh(lead)
    return lead


@pytest.fixture
def sample_template(db_session, test_tenant):
    """Create a sample email template for testing."""
    template = EmailTemplate(
        tenant_id=test_tenant.tenant_id,
        name="Test Template",
        subject="Hello {{contact_first_name}}",
        body_html="<p>Hi {{contact_first_name}},</p>",
        body_text="Hi {{contact_first_name}},",
        status=TemplateStatus.INACTIVE,
        is_default=False,
    )
    db_session.add(template)
    db_session.commit()
    db_session.refresh(template)
    return template


@pytest.fixture
def sample_mailbox(db_session, test_tenant):
    """Create a sample sender mailbox for testing."""
    mailbox = SenderMailbox(
        tenant_id=test_tenant.tenant_id,
        email="test@example.com",
        display_name="Test Sender",
        password="fake-password",
        warmup_status=WarmupStatus.COLD_READY,
        is_active=True,
        connection_status="successful",
        daily_send_limit=30,
        emails_sent_today=0,
        total_emails_sent=100,
        bounce_count=2,
        reply_count=10,
        complaint_count=0,
        warmup_days_completed=15,
    )
    db_session.add(mailbox)
    db_session.commit()
    db_session.refresh(mailbox)
    return mailbox


@pytest.fixture
def sample_warmup_profile(db_session):
    """Create a sample warmup profile for testing."""
    profile = WarmupProfile(
        name="Test Profile",
        description="A test warmup profile",
        is_default=False,
        is_system=False,
        config_json='{"phase_1_days": 7, "phase_1_min_emails": 2, "phase_1_max_emails": 5}',
    )
    db_session.add(profile)
    db_session.commit()
    db_session.refresh(profile)
    return profile


@pytest.fixture
def sample_job_run(db_session, test_tenant):
    """Create a sample job run for testing."""
    run = JobRun(
        tenant_id=test_tenant.tenant_id,
        pipeline_name="lead_sourcing",
        status=JobStatus.COMPLETED,
        triggered_by="admin@test.com",
        counters_json='{"inserted": 10, "updated": 2, "skipped": 1, "errors": 0}',
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)
    return run
