from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# 检索模式：hybrid = FTS + 向量加权合并；keyword = 仅关键词（FTS/子串）；
# vector = 仅向量。
SearchMode = Literal["hybrid", "keyword", "vector"]

DEFAULT_FTS_WEIGHT = 0.5
DEFAULT_VECTOR_WEIGHT = 0.5


class KnowledgeDocument(BaseModel):
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
