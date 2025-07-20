from __future__ import annotations

from pydantic import BaseModel

from agentforge.platform.domain.ticket import RiskLevel, TicketPriority


class ClassificationResult(BaseModel):
    intent: str
    priority: TicketPriority
    product: str | None = None
    assigned_team: str | None = None
    risk_level: RiskLevel = RiskLevel.LOW
    confidence: float = 0.8


class RuleBasedTicketClassifier:
    HIGH_RISK_TERMS = ("refund", "compensation", "complaint", "privacy", "ban")
    INCIDENT_TERMS = ("outage", "error", "unavailable", "down")
    SALES_TERMS = ("price", "purchase", "quote", "plan")

    async def classify(self, text: str) -> ClassificationResult:
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
