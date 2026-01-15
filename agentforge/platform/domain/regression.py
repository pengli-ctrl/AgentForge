"""AgentForge 平台领域模型层：regression。

本模块定义 regression 领域模型，约束业务状态、输入输出结构和跨层数据契约。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：GoldenItem、RegressionRunStatus、RegressionRun、QualityReport。
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def _utcnow() -> datetime:
    """执行 _utcnow 对应的逻辑，并返回处理结果。

    Returns:
        datetime，函数执行后的结果。
    """
    return datetime.now(timezone.utc)


class GoldenItem(BaseModel):
    """GoldenItem。

    GoldenItem 是结构化数据模型，负责承载输入、输出或持久化数据，并执行字段级校验。

    主要成员：
    - model_config: ConfigDict(extra='forbid')。
    - item_id: str。
    - tenant_id: str。
    - query: str。
    - expected_chunk_ids: list[str]。
    - expected_citations: list[str]。
    - expected_intent: str | None。
    - expected_priority: str | None。
    - expected_risk_level: str | None。
    - created_at: datetime。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    model_config = ConfigDict(extra="forbid")

    item_id: str
    tenant_id: str
    query: str
    expected_chunk_ids: list[str] = Field(default_factory=list)
    expected_citations: list[str] = Field(default_factory=list)
    expected_intent: str | None = None
    expected_priority: str | None = None
    expected_risk_level: str | None = None
    created_at: datetime = Field(default_factory=_utcnow)


class RegressionRunStatus(str, Enum):
    """RegressionRunStatus。

    RegressionRunStatus 是状态或类型枚举，用于约束系统内部取值，避免使用散落的字符串常量。

    主要成员：
    - PASSED: 'passed'。
    - FAILED: 'failed'。
    - HOLD: 'hold'。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    PASSED = "passed"
    FAILED = "failed"
    HOLD = "hold"


class RegressionRun(BaseModel):
    """RegressionRun。

    RegressionRun 是结构化数据模型，负责承载输入、输出或持久化数据，并执行字段级校验。

    主要成员：
    - model_config: ConfigDict(extra='forbid')。
    - run_id: str。
    - tenant_id: str。
    - candidate_id: str。
    - status: RegressionRunStatus。
    - recall_at_k: float。
    - citation_accuracy: float。
    - classification_accuracy: float。
    - priority_accuracy: float。
    - structured_output_rate: float。
    - high_risk_miss_rate: float。
    - verdict: str。
    - created_at: datetime。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    model_config = ConfigDict(extra="forbid")

    run_id: str
    tenant_id: str
    candidate_id: str
    status: RegressionRunStatus
    recall_at_k: float = 0.0
    citation_accuracy: float = 0.0
    classification_accuracy: float = 0.0
    priority_accuracy: float = 0.0
    structured_output_rate: float = 0.0
    high_risk_miss_rate: float = 0.0
    verdict: str = "block"
    created_at: datetime = Field(default_factory=_utcnow)


class QualityReport(BaseModel):
    """QualityReport。

    QualityReport 是结构化数据模型，负责承载输入、输出或持久化数据，并执行字段级校验。

    主要成员：
    - model_config: ConfigDict(extra='forbid')。
    - report_id: str。
    - run_id: str。
    - candidate_id: str。
    - tenant_id: str。
    - verdict: str。
    - metrics: dict[str, float]。
    - passed: list[str]。
    - warned: list[str]。
    - failed: list[str]。
    - generated_at: datetime。
    - extra: dict[str, Any]。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    model_config = ConfigDict(extra="forbid")

    report_id: str
    run_id: str
    candidate_id: str
    tenant_id: str
    verdict: str
    metrics: dict[str, float] = Field(default_factory=dict)
    passed: list[str] = Field(default_factory=list)
    warned: list[str] = Field(default_factory=list)
    failed: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=_utcnow)
    extra: dict[str, Any] = Field(default_factory=dict)
