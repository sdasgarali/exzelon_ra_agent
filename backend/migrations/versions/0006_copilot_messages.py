"""Add copilot_messages — persisted per-user AI Copilot conversation history.

Revision ID: 0006_copilot_messages
Revises: 0005_credit_topup_lots
Create Date: 2026-10-09

The in-app copilot now remembers each user's conversation across reloads and
sessions. One row per turn (user or assistant), always scoped by tenant AND user.
Idempotent: skips creation when the table already exists (e.g. created by
`Base.metadata.create_all` on a dev box before this revision ran).
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers
revision = "0006_copilot_messages"
down_revision = "0005_credit_topup_lots"
branch_labels = None
depends_on = None

TABLE = "copilot_messages"


def upgrade() -> None:
    bind = op.get_bind()
    if TABLE in sa.inspect(bind).get_table_names():
        return
    op.create_table(
        TABLE,
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("context_page", sa.String(64), nullable=True),
        # Base-class columns, present on every table in this schema.
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.tenant_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
    )
    op.create_index("ix_copilot_messages_tenant_id", TABLE, ["tenant_id"])
    op.create_index("ix_copilot_messages_user_id", TABLE, ["user_id"])
    op.create_index("ix_copilot_messages_created_at", TABLE, ["created_at"])
    op.create_index("ix_copilot_messages_is_archived", TABLE, ["is_archived"])
    op.create_index(
        "idx_copilot_msg_tenant_user_created", TABLE, ["tenant_id", "user_id", "created_at"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    if TABLE not in sa.inspect(bind).get_table_names():
        return
    op.drop_table(TABLE)
