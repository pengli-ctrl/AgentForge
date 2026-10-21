"""数据库迁移版本 0030_demo_asset。

Revision ID: 20261021_0030
Revises: 20261021_0029
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20261021_0030"
down_revision = "20261021_0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """应用当前数据库迁移版本。"""
    op.create_table(
        "module_asset_assets",
        sa.Column("asset_id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), primary_key=True),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False, server_default="general"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("created_by", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_module_asset_assets_tenant_id",
        "module_asset_assets",
        ["tenant_id"],
        unique=False,
    )


def downgrade() -> None:
    """回滚当前数据库迁移版本。"""
    op.drop_index("ix_module_asset_assets_tenant_id", table_name="module_asset_assets")
    op.drop_table("module_asset_assets")
