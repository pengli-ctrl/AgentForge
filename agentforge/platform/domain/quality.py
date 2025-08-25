from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PromptStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    DEPRECATED = "deprecated"


class ModelVersionStatus(str, Enum):
    AVAILABLE = "available"
    DEPRECATED = "deprecated"
    RETIRED = "retired"


class QualityGateVerdict(str, Enum):
    """质量门禁判定结果类型。

    PASS：所有门禁通过，可发布。
    HOLD：存在非阻塞告警（如分类准确率略低于目标但高于硬底线），可人工判断后放行。
    BLOCK：硬性失败（召回/引用/分类或高危漏报不达标），禁止发布。
    """

    PASS = "pass"
    HOLD = "hold"
    BLOCK = "block"


class PromptTemplate(BaseModel):
    """带版本标记的 Prompt 模板。

    version 遵循语义化版本；content 为模板正文，可包含 {placeholder} 占位符。
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    version: str
    content: str
    status: PromptStatus = PromptStatus.DRAFT
    # 视为"激活中"的版本；每激活一个新版本，旧的自动转 DEPRECATED
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def render(self, **kwargs: Any) -> str:
        try:
            return self.content.format(**kwargs)
        except (KeyError, IndexError) as exc:
            raise ValueError(f"Missing template placeholder for prompt {self.name}: {exc}") from exc


class ModelVersion(BaseModel):
    """带提供商与版本标识的模型版本记录，供模型路由选型与门禁追溯。"""

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
    """一次待评审的发布候选：绑定一条 Prompt 与一个模型版本。"""

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
    """一次质量门禁的判定结果，用于决定发布候选是否放行。"""

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
    """一条分类评估的 Ground-Truth 样本。

    记录客户原始提问、期望的意图/优先级/风险等级，以及该样本是否包含
    必须被结构化输出的字段（用于"结构化输出合法率"）。
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
    """单个分类样本的评估结果。"""

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
    """一次离线分类质量评估的聚合报告。"""

    model_config = ConfigDict(extra="forbid")

    sample_count: int = 0
    classification_accuracy: float = 0.0
    priority_accuracy: float = 0.0
    risk_accuracy: float = 0.0
    structured_output_rate: float = 0.0
    high_risk_miss_rate: float = 0.0
    per_sample: list[ClassificationEvaluation] = Field(default_factory=list)
