"""数据库迁移版本 0027_expense_invoice_gate_alert_occurrence。

Revision ID: 20261020_0027
Revises: 20261020_0026
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20261020_0027"
down_revision = "20261020_0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """应用当前数据库迁移版本。"""
    if op.get_bind().dialect.name != "postgresql":
        return
    op.add_column(
        "expense_invoice_gate_alerts",
        sa.Column("occurrence", sa.Integer(), nullable=False, server_default="1"),
        schema="module_expense",
    )


def downgrade() -> None:
    """回滚当前数据库迁移版本。"""
    if op.get_bind().dialect.name != "postgresql":
        return
    op.drop_column(
        "expense_invoice_gate_alerts",
        "occurrence",
        schema="module_expense",
    )
