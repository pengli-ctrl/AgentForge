"""add audit actor and trace fields

Revision ID: 20260917_0005
Revises: 20260917_0004
Create Date: 2026-09-18
"""

import sqlalchemy as sa

from alembic import op

revision = "20260917_0005"
down_revision = "20260917_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "audit_events",
        sa.Column("actor_type", sa.String(length=32), nullable=False, server_default="system"),
    )
    op.add_column(
        "audit_events",
        sa.Column("actor_id", sa.String(length=128), nullable=False, server_default="agentforge"),
    )
    op.add_column("audit_events", sa.Column("trace_id", sa.String(length=64), nullable=True))
    op.create_index("ix_audit_events_action", "audit_events", ["action"])
    op.create_index("ix_audit_events_resource_type", "audit_events", ["resource_type"])
    op.create_index("ix_audit_events_resource_id", "audit_events", ["resource_id"])
    op.create_index("ix_audit_events_trace_id", "audit_events", ["trace_id"])


def downgrade() -> None:
    op.drop_index("ix_audit_events_trace_id", table_name="audit_events")
    op.drop_index("ix_audit_events_resource_id", table_name="audit_events")
    op.drop_index("ix_audit_events_resource_type", table_name="audit_events")
    op.drop_index("ix_audit_events_action", table_name="audit_events")
    op.drop_column("audit_events", "trace_id")
    op.drop_column("audit_events", "actor_id")
    op.drop_column("audit_events", "actor_type")
