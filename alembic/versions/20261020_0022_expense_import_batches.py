"""数据库迁移版本 0022_expense_import_batches。

Revision ID: 20261020_0022
Revises: 20261020_0021
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20261020_0022"
down_revision = "20261020_0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """应用当前数据库迁移版本。"""
    if op.get_bind().dialect.name != "postgresql":
        return
    op.create_table(
        "expense_import_batches",
        sa.Column("batch_id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("total_files", sa.Integer(), nullable=False),
        sa.Column("success_count", sa.Integer(), nullable=False),
        sa.Column("failed_count", sa.Integer(), nullable=False),
        sa.Column("items", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        schema="module_expense",
    )
    op.create_index(
        "ix_expense_import_batches_tenant_id",
        "expense_import_batches",
        ["tenant_id"],
        schema="module_expense",
    )
    op.create_index(
        "ix_expense_import_batches_status",
        "expense_import_batches",
        ["status"],
        schema="module_expense",
    )


def downgrade() -> None:
    """回滚当前数据库迁移版本。"""
    if op.get_bind().dialect.name != "postgresql":
        return
    op.drop_index(
        "ix_expense_import_batches_status",
        table_name="expense_import_batches",
        schema="module_expense",
    )
    op.drop_index(
        "ix_expense_import_batches_tenant_id",
        table_name="expense_import_batches",
        schema="module_expense",
    )
    op.drop_table("expense_import_batches", schema="module_expense")
