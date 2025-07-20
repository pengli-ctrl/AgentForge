from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field

from agentforge.platform.domain.ticket import RiskLevel, TicketPriority


class EvaluationSample(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_id: str
    tenant_id: str
    source_ticket_id: str
    query: str
    draft_text: str
    final_text: str
    action: str
    reason: str = ""
    reviewer_id: str
    intent: str | None = None
    priority: TicketPriority = TicketPriority.P3
    risk_level: RiskLevel = RiskLevel.LOW
    model_name: str = ""
    provider: str = ""
    trace_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
