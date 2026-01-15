"""AgentForge 平台领域模型层：retrieval。

本模块定义 retrieval 领域模型，约束业务状态、输入输出结构和跨层数据契约。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：GoldenQuery、QueryEvaluation、RetrievalReport。
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from agentforge.platform.domain.knowledge import RetrievedChunk


class GoldenQuery(BaseModel):
    """GoldenQuery。

    GoldenQuery 是结构化数据模型，负责承载输入、输出或持久化数据，并执行字段级校验。

    主要成员：
    - model_config: ConfigDict(extra='forbid')。
    - tenant_id: str。
    - query: str。
    - expected_chunk_ids: list[str]。
    - expected_citations: list[str]。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    model_config = ConfigDict(extra="forbid")

    tenant_id: str
    query: str
    expected_chunk_ids: list[str] = Field(default_factory=list)
    expected_citations: list[str] = Field(default_factory=list)


class QueryEvaluation(BaseModel):
    """QueryEvaluation。

    QueryEvaluation 是结构化数据模型，负责承载输入、输出或持久化数据，并执行字段级校验。

    主要成员：
    - model_config: ConfigDict(extra='forbid')。
    - query: str。
    - retrieved: list[str]。
    - retrieved_chunks: list[RetrievedChunk]。
    - recall_at_k: float。
    - precision_at_k: float。
    - reciprocal_rank: float。
    - citation_accuracy: float。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
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
    """RetrievalReport。

    RetrievalReport 是结构化数据模型，负责承载输入、输出或持久化数据，并执行字段级校验。

    主要成员：
    - model_config: ConfigDict(extra='forbid')。
    - query_count: int。
    - recall_at_k: float。
    - precision_at_k: float。
    - mean_reciprocal_rank: float。
    - citation_accuracy: float。
    - k: int。
    - per_query: list[QueryEvaluation]。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    model_config = ConfigDict(extra="forbid")

    query_count: int = 0
    recall_at_k: float = 0.0
    precision_at_k: float = 0.0
    mean_reciprocal_rank: float = 0.0
    citation_accuracy: float = 0.0
    k: int = 5
    per_query: list[QueryEvaluation] = Field(default_factory=list)
