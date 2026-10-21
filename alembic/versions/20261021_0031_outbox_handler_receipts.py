"""数据库迁移版本 0031_outbox_handler_receipts。

Revision ID: 20261021_0031
Revises: 20261021_0030
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20261021_0031"
down_revision = "20261021_0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """应用当前数据库迁移版本。"""
    op.create_table(
        "outbox_handler_receipts",
        sa.Column("event_id", sa.String(length=64), primary_key=True),
        sa.Column("handler_name", sa.String(length=256), primary_key=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="processing"),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_outbox_handler_receipts_status",
        "outbox_handler_receipts",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    """回滚当前数据库迁移版本。"""
    op.drop_index("ix_outbox_handler_receipts_status", table_name="outbox_handler_receipts")
    op.drop_table("outbox_handler_receipts")
