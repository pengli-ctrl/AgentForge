"""数据库迁移版本 0021_expense_ocr_jobs。

Revision ID: 20261020_0021
Revises: 20261020_0020
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20261020_0021"
down_revision = "20261020_0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """应用当前数据库迁移版本。"""
    if op.get_bind().dialect.name != "postgresql":
        return
    op.create_table(
        "expense_ocr_jobs",
        sa.Column("job_id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("attachment_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("extraction_id", sa.String(length=64), nullable=True),
        sa.Column("error", sa.Text(), nullable=False, server_default=""),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        schema="module_expense",
    )
    op.create_index(
        "ix_expense_ocr_jobs_tenant_id",
        "expense_ocr_jobs",
        ["tenant_id"],
        schema="module_expense",
    )
    op.create_index(
        "ix_expense_ocr_jobs_attachment_id",
        "expense_ocr_jobs",
        ["attachment_id"],
        schema="module_expense",
    )
    op.create_index(
        "ix_expense_ocr_jobs_status",
        "expense_ocr_jobs",
        ["status"],
        schema="module_expense",
    )


def downgrade() -> None:
    """回滚当前数据库迁移版本。"""
    if op.get_bind().dialect.name != "postgresql":
        return
    op.drop_index(
        "ix_expense_ocr_jobs_status", table_name="expense_ocr_jobs", schema="module_expense"
    )
    op.drop_index(
        "ix_expense_ocr_jobs_attachment_id",
        table_name="expense_ocr_jobs",
        schema="module_expense",
    )
    op.drop_index(
        "ix_expense_ocr_jobs_tenant_id", table_name="expense_ocr_jobs", schema="module_expense"
    )
    op.drop_table("expense_ocr_jobs", schema="module_expense")
