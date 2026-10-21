"""数据库迁移版本 0032_saas_control_plane。

Revision ID: 20261021_0032
Revises: 20261021_0031
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20261021_0032"
down_revision = "20261021_0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """应用当前数据库迁移版本。"""
    op.create_table(
        "tenant_accounts",
        sa.Column("tenant_id", sa.String(length=64), primary_key=True),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("plan_name", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="provisioning"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("suspended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status_reason", sa.String(length=512), nullable=False, server_default=""),
    )
    op.create_index("ix_tenant_accounts_plan_name", "tenant_accounts", ["plan_name"])
    op.create_index("ix_tenant_accounts_status", "tenant_accounts", ["status"])
    op.create_table(
        "usage_records",
        sa.Column("record_id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("metric", sa.String(length=64), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=128), nullable=False, server_default="platform"),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.UniqueConstraint(
            "tenant_id",
            "idempotency_key",
            name="uq_usage_tenant_idempotency",
        ),
    )
    op.create_index("ix_usage_records_tenant_id", "usage_records", ["tenant_id"])
    op.create_index("ix_usage_records_metric", "usage_records", ["metric"])
    op.create_index("ix_usage_records_occurred_at", "usage_records", ["occurred_at"])


def downgrade() -> None:
    """回滚当前数据库迁移版本。"""
    op.drop_index("ix_usage_records_occurred_at", table_name="usage_records")
    op.drop_index("ix_usage_records_metric", table_name="usage_records")
    op.drop_index("ix_usage_records_tenant_id", table_name="usage_records")
    op.drop_table("usage_records")
    op.drop_index("ix_tenant_accounts_status", table_name="tenant_accounts")
    op.drop_index("ix_tenant_accounts_plan_name", table_name="tenant_accounts")
    op.drop_table("tenant_accounts")
