"""数据库迁移版本 0024_expense_writeback_jobs。

Revision ID: 20261020_0024
Revises: 20261020_0023
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20261020_0024"
down_revision = "20261020_0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """应用当前数据库迁移版本。"""
    if op.get_bind().dialect.name != "postgresql":
        return
    op.create_table(
        "expense_writeback_jobs",
        sa.Column("job_id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("connector_id", sa.String(length=128), nullable=False),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("actor_id", sa.String(length=128), nullable=False),
        sa.Column("claim_ids", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("total_claims", sa.Integer(), nullable=False),
        sa.Column("succeeded_claims", sa.Integer(), nullable=False),
        sa.Column("failed_claims", sa.Integer(), nullable=False),
        sa.Column("skipped_claims", sa.Integer(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=False),
        sa.Column("items", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        schema="module_expense",
    )
    op.create_index(
        "ix_expense_writeback_jobs_tenant_id",
        "expense_writeback_jobs",
        ["tenant_id"],
        schema="module_expense",
    )
    op.create_index(
        "ix_expense_writeback_jobs_connector_id",
        "expense_writeback_jobs",
        ["connector_id"],
        schema="module_expense",
    )
    op.create_index(
        "ix_expense_writeback_jobs_status",
        "expense_writeback_jobs",
        ["status"],
        schema="module_expense",
    )


def downgrade() -> None:
    """回滚当前数据库迁移版本。"""
    if op.get_bind().dialect.name != "postgresql":
        return
    op.drop_index(
        "ix_expense_writeback_jobs_status",
        table_name="expense_writeback_jobs",
        schema="module_expense",
    )
    op.drop_index(
        "ix_expense_writeback_jobs_connector_id",
        table_name="expense_writeback_jobs",
        schema="module_expense",
    )
    op.drop_index(
        "ix_expense_writeback_jobs_tenant_id",
        table_name="expense_writeback_jobs",
        schema="module_expense",
    )
    op.drop_table("expense_writeback_jobs", schema="module_expense")
