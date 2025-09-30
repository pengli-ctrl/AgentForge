"""add connector specs

Revision ID: 20260918_0009
Revises: 20260918_0008
Create Date: 2026-09-18
"""

import sqlalchemy as sa

from alembic import op

revision = "20260918_0009"
down_revision = "20260918_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "connector_specs",
        sa.Column("connector_id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False, index=True),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False, server_default="1.0"),
        sa.Column(
            "risk_level",
            sa.String(length=16),
            nullable=False,
            server_default="low",
        ),
        sa.Column("endpoint", sa.String(length=512), nullable=True),
        sa.Column("allowed_actions", sa.JSON(), nullable=False),
        sa.Column("credential", sa.JSON(), nullable=True),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("connector_specs")