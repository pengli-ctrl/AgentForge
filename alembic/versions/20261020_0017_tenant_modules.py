"""数据库迁移版本 0017_tenant_modules。

Revision ID: 20261020_0017
Revises: 20261020_0016
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20261020_0017"
down_revision = "20261020_0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """应用当前数据库迁移版本。"""
    op.create_table(
        "tenant_modules",
        sa.Column("tenant_id", sa.String(length=64), primary_key=True),
        sa.Column("module_name", sa.String(length=64), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("plan_name", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    """回滚当前数据库迁移版本。"""
    op.drop_table("tenant_modules")
