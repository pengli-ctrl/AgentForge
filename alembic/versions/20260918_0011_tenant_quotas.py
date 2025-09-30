"""add tenant quotas

Revision ID: 20260918_0011
Revises: 20260918_0010
Create Date: 2026-09-18
"""

import sqlalchemy as sa

from alembic import op

revision = "20260918_0011"
down_revision = "20260918_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenant_quotas",
        sa.Column("tenant_id", sa.String(length=64), primary_key=True),
        sa.Column("monthly_limit", sa.Float(), nullable=False, server_default="0"),
        sa.Column("warning_threshold", sa.Float(), nullable=False, server_default="0.8"),
        sa.Column("hard_limit", sa.Float(), nullable=False, server_default="1"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("tenant_quotas")