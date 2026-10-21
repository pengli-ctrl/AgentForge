"""数据库迁移版本 0023_upload_sessions。

Revision ID: 20261020_0023
Revises: 20261020_0022
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20261020_0023"
down_revision = "20261020_0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """应用当前数据库迁移版本。"""
    if op.get_bind().dialect.name != "postgresql":
        return
    op.create_table(
        "upload_sessions",
        sa.Column("upload_id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("owner_module", sa.String(length=64), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=128), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("chunk_size", sa.Integer(), nullable=False),
        sa.Column("total_chunks", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("expected_sha256", sa.String(length=64), nullable=True),
        sa.Column("completed_sha256", sa.String(length=64), nullable=True),
        sa.Column("object_key", sa.String(length=512), nullable=True),
        sa.Column("parts", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_upload_sessions_tenant_id", "upload_sessions", ["tenant_id"])
    op.create_index("ix_upload_sessions_owner_module", "upload_sessions", ["owner_module"])
    op.create_index("ix_upload_sessions_status", "upload_sessions", ["status"])
    op.create_index("ix_upload_sessions_expires_at", "upload_sessions", ["expires_at"])


def downgrade() -> None:
    """回滚当前数据库迁移版本。"""
    if op.get_bind().dialect.name != "postgresql":
        return
    op.drop_index("ix_upload_sessions_expires_at", table_name="upload_sessions")
    op.drop_index("ix_upload_sessions_status", table_name="upload_sessions")
    op.drop_index("ix_upload_sessions_owner_module", table_name="upload_sessions")
    op.drop_index("ix_upload_sessions_tenant_id", table_name="upload_sessions")
    op.drop_table("upload_sessions")
