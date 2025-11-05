"""add archived to report_runs

Revision ID: 20260918_0015
Revises: 20260918_0014
Create Date: 2026-09-18
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260918_0015"
down_revision = "20260918_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "report_runs",
        sa.Column(
            "archived",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("report_runs", "archived")