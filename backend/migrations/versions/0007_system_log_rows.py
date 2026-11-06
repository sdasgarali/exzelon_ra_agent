"""Allow system-wide log rows: nullable tenant_id on automation_events and cost_entries.

Revision ID: 0007_system_log_rows
Revises: 0006_user_terms_acceptance
Create Date: 2026-11-06

Scheduler jobs log platform-wide events (21 of 28 `log_automation_event` call sites pass
no tenant), and AI calls made by a super admin outside any workspace still cost money.
Both used to be written as `tenant_id or 1`, filing them under tenant 1, a real
workspace whose activity feed and cost reports then showed platform-wide data.
NULL now means "system": `tenant_filter` (`tenant_id == X`) hides those rows from every
tenant, and the super admin's unscoped views include them. (ELR-005 follow-up)

Existing rows are not touched: old system events filed under tenant 1 cannot be told
apart from tenant 1's own events. Making a column NULL-able is an in-place, online
change on MySQL 8 (ALGORITHM=INPLACE, concurrent DML allowed); the FK and index stay.
Idempotent: a column that is already nullable is skipped.
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers
revision = "0007_system_log_rows"
down_revision = "0006_user_terms_acceptance"
branch_labels = None
depends_on = None

TABLES = ("automation_events", "cost_entries")
COLUMN = "tenant_id"


def _column(bind, table):
    inspector = sa.inspect(bind)
    if table not in inspector.get_table_names():
        return None
    for col in inspector.get_columns(table):
        if col["name"] == COLUMN:
            return col
    return None


def upgrade() -> None:
    bind = op.get_bind()
    for table in TABLES:
        col = _column(bind, table)
        if col is None or col.get("nullable"):
            continue
        # batch mode so SQLite (no ALTER COLUMN) works too; on MySQL it is a plain MODIFY.
        with op.batch_alter_table(table) as batch:
            batch.alter_column(COLUMN, existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table in TABLES:
        col = _column(bind, table)
        if col is None or not col.get("nullable"):
            continue
        nulls = bind.execute(
            sa.text(f"SELECT COUNT(*) FROM {table} WHERE {COLUMN} IS NULL")
        ).scalar()
        if nulls:
            # Refuse rather than invent an owner for system rows (that was the bug).
            raise RuntimeError(
                f"{table} has {nulls} system rows (tenant_id IS NULL); delete or reassign "
                f"them before downgrading below 0007."
            )
        with op.batch_alter_table(table) as batch:
            batch.alter_column(COLUMN, existing_type=sa.Integer(), nullable=False)
