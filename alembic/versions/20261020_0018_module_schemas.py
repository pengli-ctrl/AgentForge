"""数据库迁移版本 0018_module_schemas。

Revision ID: 20261020_0018
Revises: 20261020_0017
"""

from __future__ import annotations

from alembic import op

revision = "20261020_0018"
down_revision = "20261020_0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """应用当前数据库迁移版本。"""
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("CREATE SCHEMA IF NOT EXISTS module_support")
    op.execute("CREATE SCHEMA IF NOT EXISTS module_expense")
    op.execute("ALTER TABLE public.tickets SET SCHEMA module_support")
    op.execute("ALTER TABLE module_support.tickets RENAME TO support_tickets")
    op.execute(
        "ALTER TABLE module_support.support_tickets "
        "RENAME CONSTRAINT uq_tickets_tenant_idempotency "
        "TO uq_support_tickets_tenant_idempotency"
    )
    op.execute(
        "ALTER INDEX module_support.ix_tickets_tenant_id " "RENAME TO ix_support_tickets_tenant_id"
    )
    op.execute("ALTER INDEX module_support.ix_tickets_status RENAME TO ix_support_tickets_status")
    op.execute("ALTER TABLE public.expense_claims SET SCHEMA module_expense")


def downgrade() -> None:
    """回滚当前数据库迁移版本。"""
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("ALTER TABLE module_expense.expense_claims SET SCHEMA public")
    op.execute("ALTER TABLE module_support.support_tickets SET SCHEMA public")
    op.execute("ALTER INDEX public.ix_support_tickets_tenant_id " "RENAME TO ix_tickets_tenant_id")
    op.execute("ALTER INDEX public.ix_support_tickets_status RENAME TO ix_tickets_status")
    op.execute(
        "ALTER TABLE public.support_tickets "
        "RENAME CONSTRAINT uq_support_tickets_tenant_idempotency "
        "TO uq_tickets_tenant_idempotency"
    )
    op.execute("ALTER TABLE public.support_tickets RENAME TO tickets")
    op.execute("DROP SCHEMA module_expense")
    op.execute("DROP SCHEMA module_support")
