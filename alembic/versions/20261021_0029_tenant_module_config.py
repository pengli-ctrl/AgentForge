"""数据库迁移版本 0029_tenant_module_config。

Revision ID: 20261021_0029
Revises: 20261020_0028
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20261021_0029"
down_revision = "20261020_0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """应用当前数据库迁移版本。"""
    op.add_column(
        "tenant_modules",
        sa.Column("config_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
    )
    op.add_column(
        "tenant_modules",
        sa.Column(
            "source",
            sa.String(length=32),
            nullable=False,
            server_default="tenant_override",
        ),
    )
    op.add_column(
        "tenant_modules",
        sa.Column("updated_by", sa.String(length=128), nullable=False, server_default=""),
    )
    op.add_column(
        "tenant_modules",
        sa.Column("config_values", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.add_column(
        "tenant_modules",
        sa.Column("secret_refs", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )


def downgrade() -> None:
    """回滚当前数据库迁移版本。"""
    op.drop_column("tenant_modules", "secret_refs")
    op.drop_column("tenant_modules", "config_values")
    op.drop_column("tenant_modules", "updated_by")
    op.drop_column("tenant_modules", "source")
    op.drop_column("tenant_modules", "config_version")
