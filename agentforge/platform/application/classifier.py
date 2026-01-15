"""AgentForge 平台应用服务层：classifier。

本模块负责 classifier 相关的平台能力，是 平台应用服务层 的组成部分。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：ClassificationResult、ClassificationModel、StructuredClassifier、RuleBasedTicketClassifier。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from agentforge.platform.domain.ticket import RiskLevel, TicketPriority

# 结构化分类输出的 Schema 语义版本。变更字段结构时递增。
# 常量：CLASSIFICATION_SCHEMA_VERSION。
CLASSIFICATION_SCHEMA_VERSION = "1.0"


class ClassificationResult(BaseModel):
    """ClassificationResult。

    ClassificationResult 是结构化数据模型，负责承载输入、输出或持久化数据，并执行字段级校验。

    主要成员：
    - model_config: ConfigDict(extra='forbid')。
    - intent: str。
    - priority: TicketPriority。
    - product: str | None。
    - assigned_team: str | None。
    - risk_level: RiskLevel。
    - confidence: float。
    - structured_valid: bool。
    - schema_version: str。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    model_config = ConfigDict(extra="forbid")

    intent: str
    priority: TicketPriority
    product: str | None = None
    assigned_team: str | None = None
    risk_level: RiskLevel = RiskLevel.LOW
    confidence: float = 0.8
    # 结构化输出合法性与 Schema 版本，用于"结构化输出合法率"评估。
    structured_valid: bool = True
    schema_version: str = CLASSIFICATION_SCHEMA_VERSION


class ClassificationModel(BaseModel):
    """ClassificationModel。

    ClassificationModel 是结构化数据模型，负责承载输入、输出或持久化数据，并执行字段级校验。

    主要成员：
    - model_config: ConfigDict(extra='forbid')。
    - text: str。
    - result: ClassificationResult。
    - raw: dict[str, Any]。
    - model_name: str。
    - provider: str。
    - prompt_version: str。
    - model_version: str。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
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
    """StructuredClassifier。

    StructuredClassifier 封装相关领域行为，保持职责单一并降低调用方复杂度。

    主要成员：
    - 方法 classify_structured()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    async def classify_structured(
        self,
        text: str,
        prompt_version: str = "",
        model_name: str = "",
        model_version: str = "",
    ) -> ClassificationModel:
        """执行 classify_structured 对应的逻辑，并返回处理结果。

        Args:
            text: str，调用方传入的 text 参数。
            prompt_version: str，调用方传入的 prompt_version 参数。
            model_name: str，调用方传入的 model_name 参数。
            model_version: str，调用方传入的 model_version 参数。

        Returns:
            ClassificationModel，函数执行后的结果。

        Raises:
            NotImplementedError: 当输入、状态或外部依赖不满足要求时抛出。
        """
        raise NotImplementedError


class RuleBasedTicketClassifier(StructuredClassifier):
    """RuleBasedTicketClassifier。

    RuleBasedTicketClassifier 封装相关领域行为，保持职责单一并降低调用方复杂度。

    主要成员：
    - HIGH_RISK_TERMS: ('refund', 'compensation', 'complaint', 'privacy', 'ban')。
    - INCIDENT_TERMS: ('outage', 'error', 'unavailable', 'down')。
    - SALES_TERMS: ('price', 'purchase', 'quote', 'plan')。
    - 方法 classify()。
    - 方法 classify_structured()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    HIGH_RISK_TERMS = ("refund", "compensation", "complaint", "privacy", "ban")
    INCIDENT_TERMS = ("outage", "error", "unavailable", "down")
    SALES_TERMS = ("price", "purchase", "quote", "plan")

    async def classify(self, text: str) -> ClassificationResult:
        """执行 classify 对应的逻辑，并返回处理结果。

        Args:
            text: str，调用方传入的 text 参数。

        Returns:
            ClassificationResult，函数执行后的结果。
        """
        result = await self._classify(text)
        return result

    async def classify_structured(
        self,
        text: str,
        prompt_version: str = "",
        model_name: str = "",
        model_version: str = "",
    ) -> ClassificationModel:
        """执行 classify_structured 对应的逻辑，并返回处理结果。

        Args:
            text: str，调用方传入的 text 参数。
            prompt_version: str，调用方传入的 prompt_version 参数。
            model_name: str，调用方传入的 model_name 参数。
            model_version: str，调用方传入的 model_version 参数。

        Returns:
            ClassificationModel，函数执行后的结果。
        """
        result = await self._classify(text)
        return ClassificationModel(
            text=text,
            result=result,
            raw={"rule_based": True},
            model_name=model_name,
            provider="rule-based",
            prompt_version=prompt_version,
            model_version=model_version,
        )

    async def _classify(self, text: str) -> ClassificationResult:
        """执行 _classify 对应的逻辑，并返回处理结果。

        Args:
            text: str，调用方传入的 text 参数。

        Returns:
            ClassificationResult，函数执行后的结果。
        """
        normalized = text.lower()
        if any(term in normalized for term in self.HIGH_RISK_TERMS):
            return ClassificationResult(
                intent="complaint_or_refund",
                priority=TicketPriority.P0,
                assigned_team="customer-success",
                risk_level=RiskLevel.HIGH,
                confidence=0.9,
            )
        if any(term in normalized for term in self.INCIDENT_TERMS):
            return ClassificationResult(
                intent="product_incident",
                priority=TicketPriority.P1,
                assigned_team="support",
                risk_level=RiskLevel.MEDIUM,
                confidence=0.85,
            )
        if any(term in normalized for term in self.SALES_TERMS):
            return ClassificationResult(
                intent="sales_question",
                priority=TicketPriority.P2,
                assigned_team="sales",
                risk_level=RiskLevel.LOW,
                confidence=0.8,
            )
        return ClassificationResult(
            intent="general_question",
            priority=TicketPriority.P3,
            assigned_team="support",
            risk_level=RiskLevel.LOW,
            confidence=0.75,
        )
