from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class GoldenItem(BaseModel):
    """一条离线 Gold 标准样本：包含期望检索命中与期望分类结果。

    用于离线回归运行器（Golden Dataset），与生产评估样本解耦，可脱离真实
    工单在线流程独立维护与回放。
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
    PASSED = "passed"
    FAILED = "failed"
    HOLD = "hold"


class RegressionRun(BaseModel):
    """一次离线回归执行记录。"""

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
    """一次离线回归产出的质量报告，可持久化存储与回查。"""

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
