from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from agentforge.platform.domain.knowledge import RetrievedChunk


class GoldenQuery(BaseModel):
    """一条用于召回评估的 Ground-Truth 查询。

    记录客户原始查询、应该被召回到的相关 chunk id 集合，
    以及该查询应产生的正确引用（用于计算引用正确率）。
    """

    model_config = ConfigDict(extra="forbid")

    tenant_id: str
    query: str
    expected_chunk_ids: list[str] = Field(default_factory=list)
    expected_citations: list[str] = Field(default_factory=list)


class QueryEvaluation(BaseModel):
    """单个查询的评估结果。"""

    model_config = ConfigDict(extra="forbid")

    query: str
    retrieved: list[str]
    retrieved_chunks: list[RetrievedChunk] = Field(default_factory=list)
    recall_at_k: float = 0.0
    precision_at_k: float = 0.0
    reciprocal_rank: float = 0.0
    citation_accuracy: float = 0.0


class RetrievalReport(BaseModel):
    """一次离线召回与引用质量评估的聚合报告。"""

    model_config = ConfigDict(extra="forbid")

    query_count: int = 0
    recall_at_k: float = 0.0
    precision_at_k: float = 0.0
    mean_reciprocal_rank: float = 0.0
    citation_accuracy: float = 0.0
    k: int = 5
    per_query: list[QueryEvaluation] = Field(default_factory=list)
