from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from agentforge.platform.domain.ticket import RiskLevel, TicketPriority

# 结构化分类输出的 Schema 语义版本。变更字段结构时递增。
CLASSIFICATION_SCHEMA_VERSION = "1.0"


class ClassificationResult(BaseModel):
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
    """一次工单理解的完整结构化输出，等价于客服场景 7.2/7.3 中对歧义。

    相比 ClassificationResult 额外保留原始输入与可选的模型/Prompt 溯源，
    供离线分类评估与质量门禁追溯。
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
    """分类器抽象。任何实现（规则/LLM/混合）都应返回结构化的 ClassificationResult。"""

    async def classify_structured(
        self,
        text: str,
        prompt_version: str = "",
        model_name: str = "",
        model_version: str = "",
    ) -> ClassificationModel:
        raise NotImplementedError


class RuleBasedTicketClassifier(StructuredClassifier):
    HIGH_RISK_TERMS = ("refund", "compensation", "complaint", "privacy", "ban")
    INCIDENT_TERMS = ("outage", "error", "unavailable", "down")
    SALES_TERMS = ("price", "purchase", "quote", "plan")

    async def classify(self, text: str) -> ClassificationResult:
        result = await self._classify(text)
        return result

    async def classify_structured(
        self,
        text: str,
        prompt_version: str = "",
        model_name: str = "",
        model_version: str = "",
    ) -> ClassificationModel:
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
