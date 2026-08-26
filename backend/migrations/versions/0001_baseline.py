"""Baseline schema (ELR-026).

Captures the entire current schema from the SQLAlchemy models via metadata, so it
matches the app exactly with no autogenerate drift. This is the starting point for
Alembic-managed migrations.

Rollout:
  * Fresh database  -> `alembic upgrade head` creates everything.
  * Existing database (schema already present via the legacy lifespan migrations)
    -> `alembic stamp 0001_baseline` marks it applied WITHOUT re-creating tables.

Going forward, schema changes are new Alembic revisions (`alembic revision -m ...`),
not ad-hoc ALTERs in main.py.
"""
from alembic import op

# revision identifiers
revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Import the models package so every table is on Base.metadata, then create
    # any that don't yet exist (checkfirst=True → safe on a partially-migrated DB).
    import app.db.models  # noqa: F401
    from app.db.base import Base
    Base.metadata.create_all(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    import app.db.models  # noqa: F401
    from app.db.base import Base
    Base.metadata.drop_all(bind=op.get_bind())
