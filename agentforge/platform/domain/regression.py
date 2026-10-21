"""回归模块。"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def _utcnow() -> datetime:
    """处理当前 UTC 时间。

    Returns:
        处理结果对象。
    """
    return datetime.now(timezone.utc)


class GoldenItem(BaseModel):
    """基准条目相关组件。

    Attributes:
        item_id: 条目ID。
        tenant_id: 租户 ID，用于数据隔离。
        query: 查询。
        expected_chunk_ids: 分块。
        expected_citations: 引用。
        expected_intent: 字段值。
        expected_priority: 优先级。
        expected_risk_level: 风险级别。
        created_at: 创建时间。
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
    """回归运行状态枚举。"""

    PASSED = "passed"
    FAILED = "failed"
    HOLD = "hold"


class RegressionRun(BaseModel):
    """回归运行相关组件。

    Attributes:
        run_id: 运行ID。
        tenant_id: 租户 ID，用于数据隔离。
        candidate_id: 候选结果ID。
        status: 当前状态。
        recall_at_k: 召回于K。
        citation_accuracy: 引用准确率。
        classification_accuracy: 分类准确率。
        priority_accuracy: 优先级准确率。
        structured_output_rate: 结构化输出速率。
        high_risk_miss_rate: 高风险速率。
        verdict: 字段值。
        created_at: 创建时间。
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
    """质量报告相关组件。

    Attributes:
        report_id: 报告ID。
        run_id: 运行ID。
        candidate_id: 候选结果ID。
        tenant_id: 租户 ID，用于数据隔离。
        verdict: 字段值。
        metrics: 指标。
        passed: 通过。
        warned: 字段值。
        failed: 失败。
        generated_at: 于。
        extra: 字段值。
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
