"""数据库迁移版本 0026_expense_invoice_gate_alert_states。

Revision ID: 20261020_0026
Revises: 20261020_0025
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20261020_0026"
down_revision = "20261020_0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """应用当前数据库迁移版本。"""
    if op.get_bind().dialect.name != "postgresql":
        return
    op.create_table(
        "expense_invoice_gate_alerts",
        sa.Column("alert_id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("alert_key", sa.Text(), nullable=False),
        sa.Column("type", sa.String(length=80), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("claim_id", sa.String(length=64), nullable=False),
        sa.Column("actor_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        schema="module_expense",
    )
    op.create_index(
        "ix_expense_invoice_gate_alerts_tenant_id",
        "expense_invoice_gate_alerts",
        ["tenant_id"],
        schema="module_expense",
    )
    op.create_index(
        "ix_expense_invoice_gate_alerts_type",
        "expense_invoice_gate_alerts",
        ["type"],
        schema="module_expense",
    )
    op.create_index(
        "ix_expense_invoice_gate_alerts_severity",
        "expense_invoice_gate_alerts",
        ["severity"],
        schema="module_expense",
    )
    op.create_index(
        "ix_expense_invoice_gate_alerts_claim_id",
        "expense_invoice_gate_alerts",
        ["claim_id"],
        schema="module_expense",
    )
    op.create_index(
        "ix_expense_invoice_gate_alerts_actor_id",
        "expense_invoice_gate_alerts",
        ["actor_id"],
        schema="module_expense",
    )
    op.create_index(
        "ix_expense_invoice_gate_alerts_status",
        "expense_invoice_gate_alerts",
        ["status"],
        schema="module_expense",
    )
    op.create_index(
        "uq_expense_invoice_gate_alerts_active_key",
        "expense_invoice_gate_alerts",
        ["tenant_id", "alert_key"],
        unique=True,
        schema="module_expense",
        postgresql_where=sa.text("status = 'active'"),
    )


def downgrade() -> None:
    """回滚当前数据库迁移版本。"""
    if op.get_bind().dialect.name != "postgresql":
        return
    for index_name in (
        "uq_expense_invoice_gate_alerts_active_key",
        "ix_expense_invoice_gate_alerts_status",
        "ix_expense_invoice_gate_alerts_actor_id",
        "ix_expense_invoice_gate_alerts_claim_id",
        "ix_expense_invoice_gate_alerts_severity",
        "ix_expense_invoice_gate_alerts_type",
        "ix_expense_invoice_gate_alerts_tenant_id",
    ):
        op.drop_index(
            index_name,
            table_name="expense_invoice_gate_alerts",
            schema="module_expense",
        )
    op.drop_table("expense_invoice_gate_alerts", schema="module_expense")
