"""数据库迁移版本 0020_expense_extractions。

Revision ID: 20261020_0020
Revises: 20261020_0019
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20261020_0020"
down_revision = "20261020_0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """应用当前数据库迁移版本。"""
    if op.get_bind().dialect.name != "postgresql":
        return
    op.create_table(
        "expense_extractions",
        sa.Column("extraction_id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("attachment_id", sa.String(length=64), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        schema="module_expense",
    )
    op.create_index(
        "ix_expense_extractions_tenant_id",
        "expense_extractions",
        ["tenant_id"],
        schema="module_expense",
    )
    op.create_index(
        "ix_expense_extractions_attachment_id",
        "expense_extractions",
        ["attachment_id"],
        schema="module_expense",
    )


def downgrade() -> None:
    """回滚当前数据库迁移版本。"""
    if op.get_bind().dialect.name != "postgresql":
        return
    op.drop_index(
        "ix_expense_extractions_attachment_id",
        table_name="expense_extractions",
        schema="module_expense",
    )
    op.drop_index(
        "ix_expense_extractions_tenant_id",
        table_name="expense_extractions",
        schema="module_expense",
    )
    op.drop_table("expense_extractions", schema="module_expense")
