"""AgentForge 平台领域模型层：quality。

本模块定义 quality 领域模型，约束业务状态、输入输出结构和跨层数据契约。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
-
主要类：PromptStatus、ModelVersionStatus、QualityGateVerdict、PromptTemplate、ModelVersion、ReleaseCandidate、QualityGateResult、ClassificationGoldenItem。
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PromptStatus(str, Enum):
    """PromptStatus。

    PromptStatus 是状态或类型枚举，用于约束系统内部取值，避免使用散落的字符串常量。

    主要成员：
    - DRAFT: 'draft'。
    - ACTIVE: 'active'。
    - DEPRECATED: 'deprecated'。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    DRAFT = "draft"
    ACTIVE = "active"
    DEPRECATED = "deprecated"


class ModelVersionStatus(str, Enum):
    """ModelVersionStatus。

    ModelVersionStatus 是状态或类型枚举，用于约束系统内部取值，避免使用散落的字符串常量。

    主要成员：
    - AVAILABLE: 'available'。
    - DEPRECATED: 'deprecated'。
    - RETIRED: 'retired'。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    AVAILABLE = "available"
    DEPRECATED = "deprecated"
    RETIRED = "retired"


class QualityGateVerdict(str, Enum):
    """QualityGateVerdict。

    QualityGateVerdict 是状态或类型枚举，用于约束系统内部取值，避免使用散落的字符串常量。

    主要成员：
    - PASS: 'pass'。
    - HOLD: 'hold'。
    - BLOCK: 'block'。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    PASS = "pass"
    HOLD = "hold"
    BLOCK = "block"


class PromptTemplate(BaseModel):
    """PromptTemplate。

    PromptTemplate 是结构化数据模型，负责承载输入、输出或持久化数据，并执行字段级校验。

    主要成员：
    - model_config: ConfigDict(extra='forbid')。
    - name: str。
    - version: str。
    - content: str。
    - status: PromptStatus。
    - created_at: datetime。
    - 方法 render()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    version: str
    content: str
    status: PromptStatus = PromptStatus.DRAFT
    # 视为"激活中"的版本；每激活一个新版本，旧的自动转 DEPRECATED
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def render(self, **kwargs: Any) -> str:
        """执行 render 对应的逻辑，并返回处理结果。

        Args:
            **kwargs: Any，调用方传入的 **kwargs 参数。

        Returns:
            str，函数执行后的结果。

        Raises:
            ValueError: 当输入、状态或外部依赖不满足要求时抛出。
        """
        try:
            return self.content.format(**kwargs)
        except (KeyError, IndexError) as exc:
            raise ValueError(f"Missing template placeholder for prompt {self.name}: {exc}") from exc


class ModelVersion(BaseModel):
    """ModelVersion。

    ModelVersion 是结构化数据模型，负责承载输入、输出或持久化数据，并执行字段级校验。

    主要成员：
    - model_config: ConfigDict(extra='forbid')。
    - name: str。
    - provider: str。
    - model_id: str。
    - version: str。
    - capability_score: float。
    - is_available: bool。
    - status: ModelVersionStatus。
    - released_at: datetime。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
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
    """ReleaseCandidate。

    ReleaseCandidate 是结构化数据模型，负责承载输入、输出或持久化数据，并执行字段级校验。

    主要成员：
    - model_config: ConfigDict(extra='forbid')。
    - candidate_id: str。
    - tenant_id: str。
    - label: str。
    - prompt_name: str。
    - prompt_version: str。
    - model_name: str。
    - model_version: str。
    - metadata: dict[str, Any]。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
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
    """QualityGateResult。

    QualityGateResult 是结构化数据模型，负责承载输入、输出或持久化数据，并执行字段级校验。

    主要成员：
    - model_config: ConfigDict(extra='forbid')。
    - verdict: QualityGateVerdict。
    - passed: list[str]。
    - warned: list[str]。
    - failed: list[str]。
    - metrics: dict[str, float]。
    - thresholds: dict[str, float]。
    - evaluated_at: datetime。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
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
    """ClassificationGoldenItem。

    ClassificationGoldenItem 是结构化数据模型，负责承载输入、输出或持久化数据，并执行字段级校验。

    主要成员：
    - model_config: ConfigDict(extra='forbid')。
    - tenant_id: str。
    - query: str。
    - expected_intent: str。
    - expected_priority: str。
    - expected_risk_level: str。
    - expect_structured: bool。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
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
    """ClassificationEvaluation。

    ClassificationEvaluation 是结构化数据模型，负责承载输入、输出或持久化数据，并执行字段级校验。

    主要成员：
    - model_config: ConfigDict(extra='forbid')。
    - query: str。
    - predicted_intent: str。
    - predicted_priority: str。
    - predicted_risk_level: str。
    - structured_valid: bool。
    - intent_correct: bool。
    - priority_correct: bool。
    - risk_correct: bool。
    - high_risk_missed: bool。
    - confidence: float。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
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
    """ClassificationReport。

    ClassificationReport 是结构化数据模型，负责承载输入、输出或持久化数据，并执行字段级校验。

    主要成员：
    - model_config: ConfigDict(extra='forbid')。
    - sample_count: int。
    - classification_accuracy: float。
    - priority_accuracy: float。
    - risk_accuracy: float。
    - structured_output_rate: float。
    - high_risk_miss_rate: float。
    - per_sample: list[ClassificationEvaluation]。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    model_config = ConfigDict(extra="forbid")

    sample_count: int = 0
    classification_accuracy: float = 0.0
    priority_accuracy: float = 0.0
    risk_accuracy: float = 0.0
    structured_output_rate: float = 0.0
    high_risk_miss_rate: float = 0.0
    per_sample: list[ClassificationEvaluation] = Field(default_factory=list)
