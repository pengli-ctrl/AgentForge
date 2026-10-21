"""数据库迁移版本 0016_expense_claims。

Revision ID: 20261020_0016
Revises: 20260918_0015
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20261020_0016"
down_revision = "20260918_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """应用当前数据库迁移版本。"""
    op.create_table(
        "expense_claims",
        sa.Column("claim_id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("applicant_id", sa.String(length=64), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="CNY"),
        sa.Column("expense_date", sa.Date(), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("invoice_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "tenant_id",
            "idempotency_key",
            name="uq_expense_claims_tenant_idempotency",
        ),
    )
    op.create_index("ix_expense_claims_tenant_id", "expense_claims", ["tenant_id"])
    op.create_index("ix_expense_claims_applicant_id", "expense_claims", ["applicant_id"])
    op.create_index("ix_expense_claims_category", "expense_claims", ["category"])
    op.create_index("ix_expense_claims_status", "expense_claims", ["status"])


def downgrade() -> None:
    """回滚当前数据库迁移版本。"""
    op.drop_index("ix_expense_claims_status", table_name="expense_claims")
    op.drop_index("ix_expense_claims_category", table_name="expense_claims")
    op.drop_index("ix_expense_claims_applicant_id", table_name="expense_claims")
    op.drop_index("ix_expense_claims_tenant_id", table_name="expense_claims")
    op.drop_table("expense_claims")
