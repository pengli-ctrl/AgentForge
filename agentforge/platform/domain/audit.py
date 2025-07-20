from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from agentforge.platform.domain.ticket import RiskLevel


class AuditEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    tenant_id: str
    action: str
    resource_type: str
    resource_id: str
    risk_level: RiskLevel = RiskLevel.LOW
    actor_type: str = "system"
    actor_id: str = "agentforge"
    trace_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
