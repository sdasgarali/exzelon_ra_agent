"""Record Terms of Service / Privacy Policy acceptance on users.

Revision ID: 0006_user_terms_acceptance
Revises: 0005_credit_topup_lots
Create Date: 2026-10-12

Self-service signup now requires `accept_terms=true` (Plan_Launch_Readiness_6.md,
L4). The moment of acceptance and the TERMS_VERSION accepted are stored on the user.
Both columns are nullable: existing users and admin-invited users have no recorded
acceptance, and nothing is backfilled (we cannot claim an acceptance that never
happened). Idempotent so it is safe on a DB where the columns already exist.
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers
revision = "0006_user_terms_acceptance"
down_revision = "0005_credit_topup_lots"
branch_labels = None
depends_on = None

TABLE = "users"
COLUMNS = (
    ("terms_accepted_at", sa.DateTime()),
    ("terms_version", sa.String(50)),
)


def _existing_columns(bind) -> set:
    inspector = sa.inspect(bind)
    if TABLE not in inspector.get_table_names():
        return set()
    return {c["name"] for c in inspector.get_columns(TABLE)}


def upgrade() -> None:
    bind = op.get_bind()
    if TABLE not in sa.inspect(bind).get_table_names():
        return
    existing = _existing_columns(bind)
    for name, type_ in COLUMNS:
        if name not in existing:
            op.add_column(TABLE, sa.Column(name, type_, nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    existing = _existing_columns(bind)
    to_drop = [name for name, _ in COLUMNS if name in existing]
    if not to_drop:
        return
    # batch mode so SQLite (no native DROP COLUMN on older versions) works too.
    with op.batch_alter_table(TABLE) as batch:
        for name in to_drop:
            batch.drop_column(name)
