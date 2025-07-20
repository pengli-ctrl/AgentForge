from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from agentforge.platform.domain.ticket import RiskLevel


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class Approval(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approval_id: str
    tenant_id: str
    ticket_id: str
    task_id: str
    risk_level: RiskLevel
    status: ApprovalStatus = ApprovalStatus.PENDING
    requested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    decided_at: datetime | None = None
    decided_by: str | None = None
    reason: str = ""
