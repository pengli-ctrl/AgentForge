"""审批模块。"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from agentforge.platform.domain.risk import RiskLevel


class ApprovalStatus(str, Enum):
    """审批状态枚举。"""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class Approval(BaseModel):
    """审批领域组件。

    Attributes:
        approval_id: 审批ID。
        tenant_id: 租户 ID，用于数据隔离。
        ticket_id: 工单ID。
        task_id: 任务ID。
        risk_level: 风险级别。
        status: 当前状态。
        requested_at: 指定于。
        decided_at: 于。
        decided_by: 由。
        reason: 变更原因。
    """

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
