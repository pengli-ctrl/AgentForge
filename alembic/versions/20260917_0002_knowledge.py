"""add knowledge tables

Revision ID: 20260917_0002
Revises: 20260917_0001
Create Date: 2026-09-17
"""

import sqlalchemy as sa

from alembic import op

revision = "20260917_0002"
down_revision = "20260917_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "knowledge_documents",
        sa.Column("document_id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False, index=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source_uri", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.create_table(
        "knowledge_chunks",
        sa.Column("chunk_id", sa.String(length=64), primary_key=True),
        sa.Column("document_id", sa.String(length=64), nullable=False, index=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False, index=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("knowledge_chunks")
    op.drop_table("knowledge_documents")
