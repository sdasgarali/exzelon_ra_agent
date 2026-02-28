"""Pytest configuration and fixtures."""
import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import StaticPool

# Set test database URL BEFORE importing app to avoid MySQL connection
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["DEBUG"] = "False"

from app.main import app
from app.db.base import Base
from app.api.deps.database import get_db
from app.core.security import get_password_hash, create_access_token
from app.db.models.user import User, UserRole

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


@pytest.fixture
def admin_user(db_session):
    """Create an admin user for testing."""
    user = User(
        email="admin@test.com",
        password_hash=get_password_hash("testpassword"),
        full_name="Admin User",
        role=UserRole.ADMIN,
        is_active=True
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def operator_user(db_session):
    """Create an operator user for testing."""
    user = User(
        email="operator@test.com",
        password_hash=get_password_hash("testpassword"),
        full_name="Operator User",
        role=UserRole.OPERATOR,
        is_active=True
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def viewer_user(db_session):
    """Create a viewer user for testing."""
    user = User(
        email="viewer@test.com",
        password_hash=get_password_hash("testpassword"),
        full_name="Viewer User",
        role=UserRole.VIEWER,
        is_active=True
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def admin_token(admin_user):
    """Create an admin JWT token."""
    return create_access_token(data={"sub": admin_user.email})


@pytest.fixture
def operator_token(operator_user):
    """Create an operator JWT token."""
    return create_access_token(data={"sub": operator_user.email})


@pytest.fixture
def viewer_token(viewer_user):
    """Create a viewer JWT token."""
    return create_access_token(data={"sub": viewer_user.email})


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
