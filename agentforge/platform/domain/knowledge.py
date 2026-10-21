"""知识模块。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# 检索模式：hybrid = FTS + 向量加权合并；keyword = 仅关键词（FTS/子串）；
# vector = 仅向量。
SearchMode = Literal["hybrid", "keyword", "vector"]

# 常量：DEFAULT_FTS_WEIGHT。
DEFAULT_FTS_WEIGHT = 0.5
# 常量：DEFAULT_VECTOR_WEIGHT。
DEFAULT_VECTOR_WEIGHT = 0.5


class KnowledgeDocument(BaseModel):
    """知识文档领域组件。

    Attributes:
        document_id: 文档ID。
        tenant_id: 租户 ID，用于数据隔离。
        title: 标题。
        content: 写入内容。
        source_uri: 来源URI。
        version: 版本号。
        metadata: 附加元数据。
        created_at: 创建时间。
    """

    model_config = ConfigDict(extra="forbid")

    document_id: str
    tenant_id: str
    title: str
    content: str
    source_uri: str = ""
    version: int = 1
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class KnowledgeChunk(BaseModel):
    """知识分块相关组件。

    Attributes:
        chunk_id: 分块ID。
        document_id: 文档ID。
        tenant_id: 租户 ID，用于数据隔离。
        content: 写入内容。
        position: 位置。
        metadata: 附加元数据。
        embedding: 字段值。
        embedding_model: 模型。
        embedding_version: 版本。
    """

    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    document_id: str
    tenant_id: str
    content: str
    position: int
    metadata: dict[str, Any] = Field(default_factory=dict)
    embedding: list[float] | None = None
    embedding_model: str | None = None
    embedding_version: int | None = None


class RetrievedChunk(BaseModel):
    """已检索分块相关组件。

    Attributes:
        chunk_id: 分块ID。
        document_id: 文档ID。
        tenant_id: 租户 ID，用于数据隔离。
        title: 标题。
        content: 写入内容。
        score: 评分。
        source_uri: 来源URI。
        mode: 模式。
        fts_score: 评分。
        vector_score: 评分。
        metadata: 附加元数据。
    """

    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    document_id: str
    tenant_id: str
    title: str
    content: str
    score: float
    source_uri: str = ""
    mode: str = "hybrid"
    fts_score: float | None = None
    vector_score: float | None = None
    metadata: dict[str, object] = Field(default_factory=dict)
