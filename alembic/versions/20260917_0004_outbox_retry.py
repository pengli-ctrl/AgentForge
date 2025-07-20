"""add outbox retry fields

Revision ID: 20260917_0004
Revises: 20260917_0003
Create Date: 2026-09-17
"""

import sqlalchemy as sa

from alembic import op

revision = "20260917_0004"
down_revision = "20260917_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "outbox_events",
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("outbox_events", sa.Column("last_error", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("outbox_events", "last_error")
    op.drop_column("outbox_events", "attempts")
