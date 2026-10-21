"""检索模块。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from agentforge.platform.domain.knowledge import RetrievedChunk


class GoldenQuery(BaseModel):
    """基准查询相关组件。

    Attributes:
        tenant_id: 租户 ID，用于数据隔离。
        query: 查询。
        expected_chunk_ids: 分块。
        expected_citations: 引用。
    """

    model_config = ConfigDict(extra="forbid")

    tenant_id: str
    query: str
    expected_chunk_ids: list[str] = Field(default_factory=list)
    expected_citations: list[str] = Field(default_factory=list)


class QueryEvaluation(BaseModel):
    """查询评估相关组件。

    Attributes:
        query: 查询。
        retrieved: 已检索。
        retrieved_chunks: 已检索分片。
        recall_at_k: 召回于K。
        precision_at_k: 精确率于K。
        reciprocal_rank: 倒数排名。
        citation_accuracy: 引用准确率。
    """

    model_config = ConfigDict(extra="forbid")

    query: str
    retrieved: list[str]
    retrieved_chunks: list[RetrievedChunk] = Field(default_factory=list)
    recall_at_k: float = 0.0
    precision_at_k: float = 0.0
    reciprocal_rank: float = 0.0
    citation_accuracy: float = 0.0


class RetrievalReport(BaseModel):
    """检索报告相关组件。

    Attributes:
        query_count: 查询数量。
        recall_at_k: 召回于K。
        precision_at_k: 精确率于K。
        mean_reciprocal_rank: 平均倒数排名。
        citation_accuracy: 引用准确率。
        k: K。
        per_query: 查询。
    """

    model_config = ConfigDict(extra="forbid")

    query_count: int = 0
    recall_at_k: float = 0.0
    precision_at_k: float = 0.0
    mean_reciprocal_rank: float = 0.0
    citation_accuracy: float = 0.0
    k: int = 5
    per_query: list[QueryEvaluation] = Field(default_factory=list)
