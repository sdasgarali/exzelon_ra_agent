"""Composite (tenant_id, sent_at) index on outreach_events for the send-quota count.

Revision ID: 0004_outreach_tenant_sent_index
Revises: 0003_tenant_credit_balances
Create Date: 2026-09-22

The monthly send quota (Phase 3.3) counts `outreach_events` once per send attempt.
`tenant_id` and `sent_at` were indexed separately, which lets the planner use one and
filter the remainder — fine at a few thousand rows, not at Max's 150,000 sends a
month, where the count runs 150,000 times over a growing table.

This is purely a performance index: no behaviour depends on it.
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers
revision = "0004_outreach_tenant_sent_index"
down_revision = "0003_tenant_credit_balances"
branch_labels = None
depends_on = None

INDEX_NAME = "idx_outreach_tenant_sent"
TABLE = "outreach_events"


def _existing(bind) -> set:
    inspector = sa.inspect(bind)
    if TABLE not in inspector.get_table_names():
        return set()
    return {ix["name"] for ix in inspector.get_indexes(TABLE)}


def upgrade() -> None:
    bind = op.get_bind()
    if INDEX_NAME in _existing(bind):
        return
    if TABLE not in sa.inspect(bind).get_table_names():
        return
    op.create_index(INDEX_NAME, TABLE, ["tenant_id", "sent_at"])


def downgrade() -> None:
    bind = op.get_bind()
    if INDEX_NAME in _existing(bind):
        op.drop_index(INDEX_NAME, table_name=TABLE)
