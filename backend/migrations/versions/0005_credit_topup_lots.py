"""Add credit_topup_lots — per-purchase top-up credits with a 12-month expiry.

Revision ID: 0005_credit_topup_lots
Revises: 0004_outreach_tenant_sent_index
Create Date: 2026-09-25

Top-ups used to be one running total that never expired. They now lapse
CREDIT_TOPUP_VALIDITY_DAYS after purchase, which needs one row per purchase.
`tenant_credit_balances.topup_credits` stays as the cached total of live lots.

Backfill: any tenant already holding top-up credits (none on prod when this was
written — Stripe was not live) gets them adopted as a single lot expiring 365 days
from the migration, so nothing held today lapses early or goes untracked.
"""
from datetime import datetime, timedelta

import sqlalchemy as sa
from alembic import op

# revision identifiers
revision = "0005_credit_topup_lots"
down_revision = "0004_outreach_tenant_sent_index"
branch_labels = None
depends_on = None

TABLE = "credit_topup_lots"


def upgrade() -> None:
    bind = op.get_bind()
    tables = sa.inspect(bind).get_table_names()
    if TABLE not in tables:
        op.create_table(
            TABLE,
            sa.Column("lot_id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("credits_purchased", sa.Float(), nullable=False),
            sa.Column("credits_remaining", sa.Float(), nullable=False),
            sa.Column("purchased_at", sa.DateTime(), nullable=False),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("expired_at", sa.DateTime(), nullable=True),
            sa.Column("reference_id", sa.String(255), nullable=True),
            # Base-class columns, present on every table in this schema.
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.tenant_id"], ondelete="CASCADE"),
        )
        op.create_index("ix_credit_topup_lots_tenant_id", TABLE, ["tenant_id"])
        op.create_index("idx_topup_lot_tenant_expiry", TABLE, ["tenant_id", "expires_at"])
        op.create_index("ix_credit_topup_lots_is_archived", TABLE, ["is_archived"])

    if "tenant_credit_balances" not in tables:
        return

    # Adopt pre-existing top-up balances that have no lot yet.
    now = datetime.utcnow()
    rows = bind.execute(sa.text(
        "SELECT b.tenant_id, b.topup_credits FROM tenant_credit_balances b "
        "WHERE b.topup_credits > 0 AND NOT EXISTS "
        "(SELECT 1 FROM credit_topup_lots l WHERE l.tenant_id = b.tenant_id)"
    )).fetchall()
    for tenant_id, credits in rows:
        bind.execute(sa.text(
            "INSERT INTO credit_topup_lots (tenant_id, credits_purchased, credits_remaining, "
            "purchased_at, expires_at, reference_id, created_at, updated_at, is_archived) "
            "VALUES (:t, :c, :c, :now, :exp, 'legacy balance (pre-expiry)', :now, :now, 0)"
        ), {"t": tenant_id, "c": float(credits), "now": now, "exp": now + timedelta(days=365)})


def downgrade() -> None:
    bind = op.get_bind()
    if TABLE not in sa.inspect(bind).get_table_names():
        return
    op.drop_table(TABLE)
