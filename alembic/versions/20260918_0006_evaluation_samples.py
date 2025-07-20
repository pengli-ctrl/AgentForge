"""add evaluation samples

Revision ID: 20260918_0006
Revises: 20260917_0005
Create Date: 2026-09-18
"""

import sqlalchemy as sa

from alembic import op

revision = "20260918_0006"
down_revision = "20260917_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "evaluation_samples",
        sa.Column("sample_id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False, index=True),
        sa.Column("source_ticket_id", sa.String(length=64), nullable=False, index=True),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("draft_text", sa.Text(), nullable=False),
        sa.Column("final_text", sa.Text(), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False, index=True),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("reviewer_id", sa.String(length=128), nullable=False),
        sa.Column("intent", sa.String(length=128), nullable=True),
        sa.Column("priority", sa.String(length=8), nullable=False),
        sa.Column("risk_level", sa.String(length=32), nullable=False),
        sa.Column("model_name", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("provider", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("trace_id", sa.String(length=64), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("evaluation_samples")
