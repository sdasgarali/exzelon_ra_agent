"""Add tenant_credit_balances — the atomic per-tenant credit counter.

Revision ID: 0003_tenant_credit_balances
Revises: 0002_plan_rename_and_max_lobs
Create Date: 2026-09-22

Closes ELR-009b. `check_credit_budget()` summed the `credit_usage` ledger and compared
the total to the plan ceiling, which is a read-then-write race — under the default
six-worker pipeline thread pool, concurrent spenders all read the same "under the
ceiling" and all proceed. This row is the lock point instead.

No backfill: `credit_metering._create_balance()` seeds a tenant's first row with the
plan allowance MINUS the ledger's month-to-date total, so an existing deployment does
not hand everyone a free refill the moment this ships.
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers
revision = "0003_tenant_credit_balances"
down_revision = "0002_plan_rename_and_max_lobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if "tenant_credit_balances" in sa.inspect(bind).get_table_names():
        return

    op.create_table(
        "tenant_credit_balances",
        sa.Column("balance_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("allowance_credits", sa.Float(), nullable=False, server_default="0"),
        sa.Column("topup_credits", sa.Float(), nullable=False, server_default="0"),
        sa.Column("period_spent", sa.Float(), nullable=False, server_default="0"),
        sa.Column("lifetime_spent", sa.Float(), nullable=False, server_default="0"),
        sa.Column("lifetime_purchased", sa.Float(), nullable=False, server_default="0"),
        sa.Column("last_spend_at", sa.DateTime(), nullable=True),
        sa.Column("last_refill_at", sa.DateTime(), nullable=True),
        # Base-class columns, present on every table in this schema.
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.tenant_id"], ondelete="CASCADE"),
        # One balance per tenant — the uniqueness is what makes "lock the row" a
        # meaningful serialisation point rather than a lock on an arbitrary row.
        sa.UniqueConstraint("tenant_id", name="uq_credit_balance_tenant"),
    )
    op.create_index("idx_credit_balance_tenant", "tenant_credit_balances", ["tenant_id"])
    op.create_index("idx_credit_balance_period", "tenant_credit_balances", ["period_start"])
    op.create_index(
        "ix_tenant_credit_balances_is_archived", "tenant_credit_balances", ["is_archived"]
    )


def downgrade() -> None:
    bind = op.get_bind()
    if "tenant_credit_balances" not in sa.inspect(bind).get_table_names():
        return
    op.drop_table("tenant_credit_balances")
