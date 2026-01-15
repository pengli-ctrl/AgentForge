"""AgentForge 平台领域模型层：knowledge。

本模块定义 knowledge 领域模型，约束业务状态、输入输出结构和跨层数据契约。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：KnowledgeDocument、KnowledgeChunk、RetrievedChunk。
"""

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
    """KnowledgeDocument。

    KnowledgeDocument 是结构化数据模型，负责承载输入、输出或持久化数据，并执行字段级校验。

    主要成员：
    - model_config: ConfigDict(extra='forbid')。
    - document_id: str。
    - tenant_id: str。
    - title: str。
    - content: str。
    - source_uri: str。
    - version: int。
    - metadata: dict[str, Any]。
    - created_at: datetime。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
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
    """KnowledgeChunk。

    KnowledgeChunk 是结构化数据模型，负责承载输入、输出或持久化数据，并执行字段级校验。

    主要成员：
    - model_config: ConfigDict(extra='forbid')。
    - chunk_id: str。
    - document_id: str。
    - tenant_id: str。
    - content: str。
    - position: int。
    - metadata: dict[str, Any]。
    - embedding: list[float] | None。
    - embedding_model: str | None。
    - embedding_version: int | None。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
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
    """RetrievedChunk。

    RetrievedChunk 是结构化数据模型，负责承载输入、输出或持久化数据，并执行字段级校验。

    主要成员：
    - model_config: ConfigDict(extra='forbid')。
    - chunk_id: str。
    - document_id: str。
    - tenant_id: str。
    - title: str。
    - content: str。
    - score: float。
    - source_uri: str。
    - mode: str。
    - fts_score: float | None。
    - vector_score: float | None。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
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
