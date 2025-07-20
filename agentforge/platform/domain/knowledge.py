from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


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


class RetrievedChunk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    document_id: str
    tenant_id: str
    title: str
    content: str
    score: float
    source_uri: str = ""
