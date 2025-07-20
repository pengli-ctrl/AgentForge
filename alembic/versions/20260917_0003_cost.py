"""add cost records

Revision ID: 20260917_0003
Revises: 20260917_0002
Create Date: 2026-09-17
"""

import sqlalchemy as sa

from alembic import op

revision = "20260917_0003"
down_revision = "20260917_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cost_records",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False, index=True),
        sa.Column("task_id", sa.String(length=64), nullable=False, index=True),
        sa.Column("model_name", sa.String(length=128), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("amount", sa.Float(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("cost_records")
