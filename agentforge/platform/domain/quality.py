"""质量模块。"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PromptStatus(str, Enum):
    """提示词状态枚举。"""

    DRAFT = "draft"
    ACTIVE = "active"
    DEPRECATED = "deprecated"


class ModelVersionStatus(str, Enum):
    """模型版本状态枚举。"""

    AVAILABLE = "available"
    DEPRECATED = "deprecated"
    RETIRED = "retired"


class QualityGateVerdict(str, Enum):
    """质量门禁状态枚举。"""

    PASS = "pass"
    HOLD = "hold"
    BLOCK = "block"


class PromptTemplate(BaseModel):
    """提示词模板相关组件。

    Attributes:
        name: 名称。
        version: 版本号。
        content: 写入内容。
        status: 当前状态。
        created_at: 创建时间。
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    version: str
    content: str
    status: PromptStatus = PromptStatus.DRAFT
    # 视为"激活中"的版本；每激活一个新版本，旧的自动转 DEPRECATED
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def render(self, **kwargs: Any) -> str:
        """渲染提示词模板。

        Args:
            kwargs: 关键字参数。

        Returns:
            字符串结果。

        Raises:
            ValueError: 输入值或业务状态不合法时抛出。
        """
        try:
            return self.content.format(**kwargs)
        except (KeyError, IndexError) as exc:
            raise ValueError(f"Missing template placeholder for prompt {self.name}: {exc}") from exc


class ModelVersion(BaseModel):
    """模型版本领域组件。

    Attributes:
        name: 名称。
        provider: 提供方。
        model_id: 模型ID。
        version: 版本号。
        capability_score: 能力评分。
        is_available: 是否可用。
        status: 当前状态。
        released_at: 已释放于。
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    provider: str
    model_id: str
    version: str
    capability_score: float = 0.0
    is_available: bool = True
    status: ModelVersionStatus = ModelVersionStatus.AVAILABLE
    released_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ReleaseCandidate(BaseModel):
    """释放候选结果相关组件。

    Attributes:
        candidate_id: 候选结果ID。
        tenant_id: 租户 ID，用于数据隔离。
        label: 标签。
        prompt_name: 提示词名称。
        prompt_version: 提示词版本。
        model_name: 模型名称。
        model_version: 模型版本。
        metadata: 附加元数据。
    """

    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    tenant_id: str
    label: str = ""
    prompt_name: str
    prompt_version: str
    model_name: str
    model_version: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class QualityGateResult(BaseModel):
    """质量门禁结果相关组件。

    Attributes:
        verdict: 字段值。
        passed: 通过。
        warned: 字段值。
        failed: 失败。
        metrics: 指标。
        thresholds: 阈值。
        evaluated_at: 于。
    """

    model_config = ConfigDict(extra="forbid")

    verdict: QualityGateVerdict
    passed: list[str] = Field(default_factory=list)
    warned: list[str] = Field(default_factory=list)
    failed: list[str] = Field(default_factory=list)
    # 门禁各项的量化得分（如 recall_at_k、citation_accuracy、classification_accuracy 等）
    metrics: dict[str, float] = Field(default_factory=dict)
    thresholds: dict[str, float] = Field(default_factory=dict)
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ClassificationGoldenItem(BaseModel):
    """分类基准条目相关组件。

    Attributes:
        tenant_id: 租户 ID，用于数据隔离。
        query: 查询。
        expected_intent: 字段值。
        expected_priority: 优先级。
        expected_risk_level: 风险级别。
        expect_structured: 结构化。
    """

    model_config = ConfigDict(extra="forbid")

    tenant_id: str
    query: str
    expected_intent: str
    expected_priority: str
    expected_risk_level: str = "low"
    # 该样本是否期望输出为合法的结构化 JSON（含所有必填字段）。
    expect_structured: bool = True


class ClassificationEvaluation(BaseModel):
    """分类评估相关组件。

    Attributes:
        query: 查询。
        predicted_intent: 字段值。
        predicted_priority: 优先级。
        predicted_risk_level: 风险级别。
        structured_valid: 结构化有效。
        intent_correct: 正确。
        priority_correct: 优先级正确。
        risk_correct: 风险正确。
        high_risk_missed: 高风险。
        confidence: 字段值。
    """

    model_config = ConfigDict(extra="forbid")

    query: str
    predicted_intent: str
    predicted_priority: str
    predicted_risk_level: str
    structured_valid: bool = True
    intent_correct: bool
    priority_correct: bool
    risk_correct: bool
    high_risk_missed: bool = False
    confidence: float = 0.0


class ClassificationReport(BaseModel):
    """分类报告相关组件。

    Attributes:
        sample_count: 样本数量。
        classification_accuracy: 分类准确率。
        priority_accuracy: 优先级准确率。
        risk_accuracy: 风险准确率。
        structured_output_rate: 结构化输出速率。
        high_risk_miss_rate: 高风险速率。
        per_sample: 样本。
    """

    model_config = ConfigDict(extra="forbid")

    sample_count: int = 0
    classification_accuracy: float = 0.0
    priority_accuracy: float = 0.0
    risk_accuracy: float = 0.0
    structured_output_rate: float = 0.0
    high_risk_miss_rate: float = 0.0
    per_sample: list[ClassificationEvaluation] = Field(default_factory=list)
