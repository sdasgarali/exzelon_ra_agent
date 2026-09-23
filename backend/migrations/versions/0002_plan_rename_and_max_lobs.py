"""Rename tenant plans to free/pro/max/custom and add tenants.max_lobs.

Revision ID: 0002_plan_rename_and_max_lobs
Revises: 0001_baseline
Create Date: 2026-09-22

Two changes, both driven by `Plan_Credit_System_And_Pricing.md`:

1. `tenants.plan` moves from starter/professional/enterprise to free/pro/max/custom.
   Existing rows map starter->free, professional->pro, enterprise->max. `custom` is
   new and unused until a contract is signed.

2. `tenants.max_lobs` is added. Lines of business were never a metered resource — the
   other five `max_*` columns existed but this one did not — so the Max tier's 25-LOB
   cap had nothing to check against.

The limit columns are deliberately NOT backfilled. `core.plans.limits_for_tenant()`
resolves `max(row, plan floor)`, so rows still carrying the old all-zero defaults
self-heal to their plan's numbers with no data migration, and any tenant that was
granted higher limits by hand keeps them.
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers
revision = "0002_plan_rename_and_max_lobs"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


OLD_VALUES = ("starter", "professional", "enterprise")
NEW_VALUES = ("free", "pro", "max", "custom")
FORWARD = {"starter": "free", "professional": "pro", "enterprise": "max"}
BACKWARD = {"free": "starter", "pro": "professional", "max": "enterprise", "custom": "enterprise"}


def _enum_sql(values) -> str:
    return ", ".join(f"'{v}'" for v in values)


def _widen(dialect, values) -> None:
    """Allow `values` in tenants.plan before the data is rewritten.

    Only MySQL and Postgres constrain the column. SQLAlchemy 2.0 emits Enum without a
    CHECK constraint on SQLite (create_constraint defaults to False), so SQLite stores
    a plain VARCHAR and needs no widening at all.
    """
    if dialect == "mysql":
        op.execute(
            f"ALTER TABLE tenants MODIFY COLUMN plan ENUM({_enum_sql(values)}) NOT NULL"
        )
    elif dialect == "postgresql":
        # The enum type is named after the Python class by default.
        for v in values:
            op.execute(f"ALTER TYPE tenantplan ADD VALUE IF NOT EXISTS '{v}'")


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    # --- 1. plan rename -------------------------------------------------
    # Widen to the union first so the UPDATE can never write an illegal value.
    _widen(dialect, tuple(OLD_VALUES) + NEW_VALUES)

    for old, new in FORWARD.items():
        op.execute(sa.text("UPDATE tenants SET plan = :new WHERE plan = :old").bindparams(new=new, old=old))

    # Narrow to the final set. Postgres cannot drop a value from an enum type in
    # place, so the legacy labels stay defined but unused — harmless, and they make
    # the one-release backward-compatibility window explicit.
    if dialect == "mysql":
        op.execute(
            f"ALTER TABLE tenants MODIFY COLUMN plan ENUM({_enum_sql(NEW_VALUES)}) "
            "NOT NULL DEFAULT 'free'"
        )

    # --- 2. max_lobs ----------------------------------------------------
    cols = {c["name"] for c in sa.inspect(bind).get_columns("tenants")}
    if "max_lobs" not in cols:
        # server_default MUST be 0, not 1. Every limit column is "0 = not configured,
        # use the plan's number" and "> 0 = an explicit per-tenant cap". Backfilling 1
        # would stamp an explicit one-LOB cap onto every existing tenant — including
        # Max customers entitled to 25 — because an explicit value beats the plan.
        op.add_column(
            "tenants",
            sa.Column("max_lobs", sa.Integer(), nullable=False, server_default="0"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    cols = {c["name"] for c in sa.inspect(bind).get_columns("tenants")}
    if "max_lobs" in cols:
        op.drop_column("tenants", "max_lobs")

    _widen(dialect, tuple(OLD_VALUES) + NEW_VALUES)

    # `custom` has no pre-rename equivalent; it collapses onto enterprise, which was
    # the closest thing to an unbounded tier.
    for new, old in BACKWARD.items():
        op.execute(sa.text("UPDATE tenants SET plan = :old WHERE plan = :new").bindparams(old=old, new=new))

    if dialect == "mysql":
        op.execute(
            f"ALTER TABLE tenants MODIFY COLUMN plan ENUM({_enum_sql(OLD_VALUES)}) "
            "NOT NULL DEFAULT 'starter'"
        )
