"""Database seeding utilities."""
import structlog
from sqlalchemy.orm import Session

logger = structlog.get_logger()


def seed_admin_user(db: Session) -> None:
    """Create a default super admin user if no super_admin or admin exists.

    Uses environment variables ADMIN_EMAIL and ADMIN_PASSWORD if set,
    otherwise creates admin@example.com with a generated password.
    """
    import os
    from app.db.models.user import User, UserRole
    from app.core.security import get_password_hash

    # Check for existing super_admin or admin
    existing_super = db.query(User).filter(
        User.role == UserRole.SUPER_ADMIN
    ).first()
    if existing_super:
        return

    existing_admin = db.query(User).filter(
        User.role == UserRole.ADMIN
    ).first()
    if existing_admin:
        return

    admin_email = os.environ.get("ADMIN_EMAIL", "admin@example.com")
    admin_password = os.environ.get("ADMIN_PASSWORD", "")

    if not admin_password:
        import secrets
        admin_password = secrets.token_urlsafe(16)
        logger.warning(
            "No ADMIN_PASSWORD set. Generated temporary super admin password.",
            email=admin_email,
            password=admin_password,
            note="Change this password immediately and set ADMIN_PASSWORD env var"
        )

    admin = User(
        email=admin_email,
        password_hash=get_password_hash(admin_password),
        full_name="Super Administrator",
        role=UserRole.SUPER_ADMIN,
        is_active=True,
    )
    db.add(admin)
    db.commit()
    logger.info("Seeded default super admin user", email=admin_email)
