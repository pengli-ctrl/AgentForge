"""数据库迁移版本 0019_expense_attachments。

Revision ID: 20261020_0019
Revises: 20261020_0018
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20261020_0019"
down_revision = "20261020_0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """应用当前数据库迁移版本。"""
    if op.get_bind().dialect.name != "postgresql":
        return
    op.create_table(
        "expense_attachments",
        sa.Column("attachment_id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("claim_id", sa.String(length=64), nullable=True),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=128), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("object_key", sa.String(length=512), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "tenant_id",
            "object_key",
            name="uq_expense_attachments_tenant_object_key",
        ),
        schema="module_expense",
    )
    op.create_index(
        "ix_expense_attachments_tenant_id",
        "expense_attachments",
        ["tenant_id"],
        schema="module_expense",
    )
    op.create_index(
        "ix_expense_attachments_claim_id",
        "expense_attachments",
        ["claim_id"],
        schema="module_expense",
    )
    op.create_index(
        "ix_expense_attachments_sha256",
        "expense_attachments",
        ["sha256"],
        schema="module_expense",
    )


def downgrade() -> None:
    """回滚当前数据库迁移版本。"""
    if op.get_bind().dialect.name != "postgresql":
        return
    op.drop_index(
        "ix_expense_attachments_sha256",
        table_name="expense_attachments",
        schema="module_expense",
    )
    op.drop_index(
        "ix_expense_attachments_claim_id",
        table_name="expense_attachments",
        schema="module_expense",
    )
    op.drop_index(
        "ix_expense_attachments_tenant_id",
        table_name="expense_attachments",
        schema="module_expense",
    )
    op.drop_table("expense_attachments", schema="module_expense")
