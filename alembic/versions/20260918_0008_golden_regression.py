"""add golden items and regression runs

Revision ID: 20260918_0008
Revises: 20260918_0007
Create Date: 2026-09-18
"""

import sqlalchemy as sa

from alembic import op

revision = "20260918_0008"
down_revision = "20260918_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "golden_items",
        sa.Column("item_id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False, index=True),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("expected_chunk_ids", sa.JSON(), nullable=False),
        sa.Column("expected_citations", sa.JSON(), nullable=False),
        sa.Column("expected_intent", sa.String(length=128), nullable=True),
        sa.Column("expected_priority", sa.String(length=8), nullable=True),
        sa.Column("expected_risk_level", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "regression_runs",
        sa.Column("run_id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False, index=True),
        sa.Column("candidate_id", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("recall_at_k", sa.Float(), nullable=False, server_default="0"),
        sa.Column("citation_accuracy", sa.Float(), nullable=False, server_default="0"),
        sa.Column("classification_accuracy", sa.Float(), nullable=False, server_default="0"),
        sa.Column("priority_accuracy", sa.Float(), nullable=False, server_default="0"),
        sa.Column("structured_output_rate", sa.Float(), nullable=False, server_default="0"),
        sa.Column("high_risk_miss_rate", sa.Float(), nullable=False, server_default="0"),
        sa.Column("verdict", sa.String(length=16), nullable=False, server_default="block"),
        sa.Column("report", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("regression_runs")
    op.drop_table("golden_items")
