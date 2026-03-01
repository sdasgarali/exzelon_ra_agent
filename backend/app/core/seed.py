"""Database seeding utilities."""
import structlog
from sqlalchemy.orm import Session

logger = structlog.get_logger()


def seed_default_tenant(db: Session) -> None:
    """Create the default tenant if it doesn't exist.

    Tenant ID 1 is the 'Smart Agentic AI Cold Email Pro' tenant
    that all existing data migrates to.
    """
    from app.db.models.tenant import Tenant

    existing = db.query(Tenant).filter(Tenant.tenant_id == 1).first()
    if existing:
        return

    tenant = Tenant(
        tenant_id=1,
        name="Smart Cold Email AI Agent Pro",
        slug="smart-cold-email-ai-agent-pro",
        is_active=True,
        max_users=50,
        max_mailboxes=100,
        plan="premium",
    )
    db.add(tenant)
    db.commit()
    logger.info("Seeded default tenant", tenant_id=1, name=tenant.name)


def seed_admin_user(db: Session) -> None:
    """Create a default admin user if no admin exists.

    Uses environment variables ADMIN_EMAIL and ADMIN_PASSWORD if set,
    otherwise creates admin@example.com with a generated password.
    Assigns them to tenant_id=1 with TENANT_ADMIN role.
    """
    import os
    from app.db.models.user import User, UserRole
    from app.core.security import get_password_hash

    # Check for any admin (legacy ADMIN or TENANT_ADMIN)
    existing_admin = db.query(User).filter(
        User.role.in_([UserRole.ADMIN, UserRole.TENANT_ADMIN])
    ).first()
    if existing_admin:
        # Migrate legacy ADMIN to TENANT_ADMIN + assign tenant if missing
        if existing_admin.role == UserRole.ADMIN:
            existing_admin.role = UserRole.TENANT_ADMIN
            if not existing_admin.tenant_id:
                existing_admin.tenant_id = 1
            db.commit()
            logger.info("Migrated legacy admin to TENANT_ADMIN", email=existing_admin.email)
        elif not existing_admin.tenant_id:
            existing_admin.tenant_id = 1
            db.commit()
        return

    admin_email = os.environ.get("ADMIN_EMAIL", "admin@example.com")
    admin_password = os.environ.get("ADMIN_PASSWORD", "")

    if not admin_password:
        import secrets
        admin_password = secrets.token_urlsafe(16)
        logger.warning(
            "No ADMIN_PASSWORD set. Generated temporary admin password.",
            email=admin_email,
            password=admin_password,
            note="Change this password immediately and set ADMIN_PASSWORD env var"
        )

    admin = User(
        email=admin_email,
        password_hash=get_password_hash(admin_password),
        full_name="System Administrator",
        role=UserRole.TENANT_ADMIN,
        is_active=True,
        tenant_id=1,
    )
    db.add(admin)
    db.commit()
    logger.info("Seeded default tenant admin user", email=admin_email, tenant_id=1)


def seed_super_admin(db: Session) -> None:
    """Create the Global Super Admin user if it doesn't exist.

    Global Super Admin has tenant_id=1 (master tenant).
    Uses SUPER_ADMIN_EMAIL and SUPER_ADMIN_PASSWORD env vars.
    """
    import os
    from app.db.models.user import User, UserRole
    from app.core.security import get_password_hash
    from app.core.constants import MASTER_TENANT_ID

    existing = db.query(User).filter(User.role == UserRole.SUPER_ADMIN).first()
    if existing:
        # Migrate: ensure existing SA has tenant_id = MASTER_TENANT_ID
        if existing.tenant_id is None:
            existing.tenant_id = MASTER_TENANT_ID
            db.commit()
            logger.info("Migrated super admin to master tenant", email=existing.email, tenant_id=MASTER_TENANT_ID)
        return

    sa_email = os.environ.get("SUPER_ADMIN_EMAIL", "")
    sa_password = os.environ.get("SUPER_ADMIN_PASSWORD", "")

    if not sa_email or not sa_password:
        logger.info("SUPER_ADMIN_EMAIL/SUPER_ADMIN_PASSWORD not set — skipping super admin seed")
        return

    super_admin = User(
        email=sa_email,
        password_hash=get_password_hash(sa_password),
        full_name="Super Administrator",
        role=UserRole.SUPER_ADMIN,
        is_active=True,
        tenant_id=MASTER_TENANT_ID,
    )
    db.add(super_admin)
    db.commit()
    logger.info("Seeded global super admin user", email=sa_email, tenant_id=MASTER_TENANT_ID)
