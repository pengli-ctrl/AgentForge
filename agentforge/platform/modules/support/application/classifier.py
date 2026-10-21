"""分类器模块。"""

from __future__ import annotations

from agentforge.platform.domain.classification import (
    ClassificationModel,
    ClassificationResult,
    StructuredClassifier,
)
from agentforge.platform.domain.priority import PriorityLevel
from agentforge.platform.domain.risk import RiskLevel


class RuleBasedTicketClassifier(StructuredClassifier):
    """规则工单分类器相关组件。"""

    HIGH_RISK_TERMS = ("refund", "compensation", "complaint", "privacy", "ban")
    INCIDENT_TERMS = ("outage", "error", "unavailable", "down")
    SALES_TERMS = ("price", "purchase", "quote", "plan")

    async def classify(self, text: str) -> ClassificationResult:
        """分类规则工单分类器。

        Args:
            text: 待处理文本。

        Returns:
            分类结果结果。
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
        """分类结构化。

        Args:
            text: 待处理文本。
            prompt_version: 提示词版本。
            model_name: 模型名称。
            model_version: 模型版本。

        Returns:
            分类模型结果。
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
        """分类规则工单分类器。

        Args:
            text: 待处理文本。

        Returns:
            分类结果结果。
        """
        normalized = text.lower()
        if any(term in normalized for term in self.HIGH_RISK_TERMS):
            return ClassificationResult(
                intent="complaint_or_refund",
                priority=PriorityLevel.P0,
                assigned_team="customer-success",
                risk_level=RiskLevel.HIGH,
                confidence=0.9,
            )
        if any(term in normalized for term in self.INCIDENT_TERMS):
            return ClassificationResult(
                intent="product_incident",
                priority=PriorityLevel.P1,
                assigned_team="support",
                risk_level=RiskLevel.MEDIUM,
                confidence=0.85,
            )
        if any(term in normalized for term in self.SALES_TERMS):
            return ClassificationResult(
                intent="sales_question",
                priority=PriorityLevel.P2,
                assigned_team="sales",
                risk_level=RiskLevel.LOW,
                confidence=0.8,
            )
        return ClassificationResult(
            intent="general_question",
            priority=PriorityLevel.P3,
            assigned_team="support",
            risk_level=RiskLevel.LOW,
            confidence=0.75,
        )
