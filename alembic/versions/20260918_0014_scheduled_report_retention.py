"""add retention_days to scheduled_reports

Revision ID: 20260918_0014
Revises: 20260918_0013
Create Date: 2026-09-18
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260918_0014"
down_revision = "20260918_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "scheduled_reports",
        sa.Column("retention_days", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("scheduled_reports", "retention_days")
