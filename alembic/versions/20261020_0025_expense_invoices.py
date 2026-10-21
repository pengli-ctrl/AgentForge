"""数据库迁移版本 0025_expense_invoices。

Revision ID: 20261020_0025
Revises: 20261020_0024
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20261020_0025"
down_revision = "20261020_0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """应用当前数据库迁移版本。"""
    if op.get_bind().dialect.name != "postgresql":
        return
    op.create_table(
        "expense_invoices",
        sa.Column("invoice_id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("claim_id", sa.String(length=64), nullable=False),
        sa.Column("duplicate_key", sa.String(length=64), nullable=True),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("invoice_code", sa.String(length=64), nullable=False),
        sa.Column("invoice_number", sa.String(length=128), nullable=False),
        sa.Column("invoice_date", sa.Date(), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("seller_tax_id", sa.String(length=64), nullable=False),
        sa.Column("buyer_tax_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("verification_status", sa.String(length=32), nullable=False),
        sa.Column("verification_provider", sa.String(length=128), nullable=False),
        sa.Column("verification_ref", sa.String(length=128), nullable=False),
        sa.Column("verification_message", sa.Text(), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("release_reason", sa.Text(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "tenant_id",
            "duplicate_key",
            name="uq_expense_invoices_tenant_duplicate_key",
        ),
        schema="module_expense",
    )
    op.create_index(
        "ix_expense_invoices_tenant_id",
        "expense_invoices",
        ["tenant_id"],
        schema="module_expense",
    )
    op.create_index(
        "ix_expense_invoices_claim_id",
        "expense_invoices",
        ["claim_id"],
        schema="module_expense",
    )
    op.create_index(
        "ix_expense_invoices_fingerprint",
        "expense_invoices",
        ["fingerprint"],
        schema="module_expense",
    )
    op.create_index(
        "ix_expense_invoices_invoice_number",
        "expense_invoices",
        ["invoice_number"],
        schema="module_expense",
    )
    op.create_index(
        "ix_expense_invoices_seller_tax_id",
        "expense_invoices",
        ["seller_tax_id"],
        schema="module_expense",
    )
    op.create_index(
        "ix_expense_invoices_status",
        "expense_invoices",
        ["status"],
        schema="module_expense",
    )
    op.create_index(
        "ix_expense_invoices_verification_status",
        "expense_invoices",
        ["verification_status"],
        schema="module_expense",
    )


def downgrade() -> None:
    """回滚当前数据库迁移版本。"""
    if op.get_bind().dialect.name != "postgresql":
        return
    for index_name in (
        "ix_expense_invoices_verification_status",
        "ix_expense_invoices_status",
        "ix_expense_invoices_seller_tax_id",
        "ix_expense_invoices_invoice_number",
        "ix_expense_invoices_fingerprint",
        "ix_expense_invoices_claim_id",
        "ix_expense_invoices_tenant_id",
    ):
        op.drop_index(index_name, table_name="expense_invoices", schema="module_expense")
    op.drop_table("expense_invoices", schema="module_expense")
