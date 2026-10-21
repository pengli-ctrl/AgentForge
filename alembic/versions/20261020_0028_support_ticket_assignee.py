"""数据库迁移版本 0028_support_ticket_assignee。

Revision ID: 20261020_0028
Revises: 20261020_0027
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20261020_0028"
down_revision = "20261020_0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """应用当前数据库迁移版本。"""
    if op.get_bind().dialect.name != "postgresql":
        return
    op.add_column(
        "support_tickets",
        sa.Column("assignee_id", sa.String(length=64), nullable=True),
        schema="module_support",
    )
    op.create_index(
        "ix_support_tickets_assignee_id",
        "support_tickets",
        ["assignee_id"],
        schema="module_support",
    )


def downgrade() -> None:
    """回滚当前数据库迁移版本。"""
    if op.get_bind().dialect.name != "postgresql":
        return
    op.drop_index(
        "ix_support_tickets_assignee_id",
        table_name="support_tickets",
        schema="module_support",
    )
    op.drop_column("support_tickets", "assignee_id", schema="module_support")
