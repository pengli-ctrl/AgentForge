"""分类模块。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from agentforge.platform.domain.priority import PriorityLevel
from agentforge.platform.domain.risk import RiskLevel

# 结构化分类输出的 Schema 语义版本。变更字段结构时递增。
# 常量：CLASSIFICATION_SCHEMA_VERSION。
CLASSIFICATION_SCHEMA_VERSION = "1.0"


class ClassificationResult(BaseModel):
    """分类结果相关组件。

    Attributes:
        intent: 字段值。
        priority: 优先级。
        product: 字段值。
        assigned_team: 字段值。
        risk_level: 风险级别。
        confidence: 字段值。
        structured_valid: 结构化有效。
        schema_version: 结构版本。
    """

    model_config = ConfigDict(extra="forbid")

    intent: str
    priority: PriorityLevel
    product: str | None = None
    assigned_team: str | None = None
    risk_level: RiskLevel = RiskLevel.LOW
    confidence: float = 0.8
    # 结构化输出合法性与 Schema 版本，用于"结构化输出合法率"评估。
    structured_valid: bool = True
    schema_version: str = CLASSIFICATION_SCHEMA_VERSION


class ClassificationModel(BaseModel):
    """分类模型相关组件。

    Attributes:
        text: 文本。
        result: 处理结果。
        raw: 字段值。
        model_name: 模型名称。
        provider: 提供方。
        prompt_version: 提示词版本。
        model_version: 模型版本。
    """

    model_config = ConfigDict(extra="forbid")

    text: str
    result: ClassificationResult
    raw: dict[str, Any] = {}
    model_name: str = ""
    provider: str = ""
    prompt_version: str = ""
    model_version: str = ""


class StructuredClassifier:
    """结构化分类器相关组件。"""

    async def classify_structured(
        self,
        text: str,
        prompt_version: str = "",
        model_name: str = "",
        model_version: str = "",
    ) -> ClassificationModel:
        """分类结构化。

        Args:
            text: 待处理文本。
            prompt_version: 提示词版本。
            model_name: 模型名称。
            model_version: 模型版本。

        Raises:
            NotImplementedError: 操作无法完成时抛出。

        Returns:
            分类模型结果。
        """
        raise NotImplementedError
