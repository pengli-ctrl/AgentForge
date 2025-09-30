"""report_runs

Revision ID: 20260918_0013
Revises: 20260918_0012
Create Date: 2026-09-18
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "20260918_0013"
down_revision = "20260918_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "report_runs",
        sa.Column("run_id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("report_type", sa.String(length=16), nullable=False),
        sa.Column("format", sa.String(length=8), nullable=False, server_default="json"),
        sa.Column("rows", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("summary", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("scheduled_report_id", sa.String(length=64), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_report_runs_tenant_id", "report_runs", ["tenant_id"])
    op.create_index("ix_report_runs_report_type", "report_runs", ["report_type"])
    op.create_index("ix_report_runs_scheduled_report_id", "report_runs", ["scheduled_report_id"])
    op.create_index("ix_report_runs_generated_at", "report_runs", ["generated_at"])


def downgrade() -> None:
    op.drop_index("ix_report_runs_generated_at", table_name="report_runs")
    op.drop_index("ix_report_runs_scheduled_report_id", table_name="report_runs")
    op.drop_index("ix_report_runs_report_type", table_name="report_runs")
    op.drop_index("ix_report_runs_tenant_id", table_name="report_runs")
    op.drop_table("report_runs")
