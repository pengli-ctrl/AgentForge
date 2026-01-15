"""AgentForge 数据库迁移层：20260918_0007_knowledge_hybrid。

本模块负责 20260918_0007_knowledge_hybrid 相关能力，是 数据库迁移层 的组成部分。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 涉及租户、任务、审计或成本的数据必须保持隔离和可追踪。
- 关键路径应保留日志、指标或链路追踪信息。
- 主要函数：upgrade、downgrade。
"""

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

from agentforge.platform.application.knowledge_embedder import EMBEDDING_DIM
from alembic import op

revision = "20260918_0007"
down_revision = "20260918_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. 为 chunk 增加向量列与 embedding 版本字段
    """执行 upgrade 对应的逻辑，并返回处理结果。

    Returns:
        None，函数执行后的结果。
    """
    op.add_column(
        "knowledge_chunks",
        sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=True),
    )
    op.add_column(
        "knowledge_chunks",
        sa.Column("embedding_model", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "knowledge_chunks",
        sa.Column("embedding_version", sa.Integer(), nullable=True),
    )

    # 2. PostgreSQL FTS 全文索引（GIN，基于 content 的计算列）
    op.execute("""
        CREATE INDEX ix_knowledge_chunks_fts_content
        ON knowledge_chunks
        USING gin (to_tsvector('english', content))
        """)

    # 3. pgvector 向量索引（HNSW，适用于高维近似最近邻）
    op.execute("""
        CREATE INDEX ix_knowledge_chunks_embedding_hnsw
        ON knowledge_chunks
        USING hnsw (embedding vector_cosine_ops)
        """)


def downgrade() -> None:
    """执行 downgrade 对应的逻辑，并返回处理结果。

    Returns:
        None，函数执行后的结果。
    """
    op.execute("DROP INDEX IF EXISTS ix_knowledge_chunks_embedding_hnsw")
    op.execute("DROP INDEX IF EXISTS ix_knowledge_chunks_fts_content")
    op.drop_column("knowledge_chunks", "embedding_version")
    op.drop_column("knowledge_chunks", "embedding_model")
    op.drop_column("knowledge_chunks", "embedding")
