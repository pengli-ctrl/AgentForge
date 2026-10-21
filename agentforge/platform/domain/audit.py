"""审计模块。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from agentforge.platform.domain.risk import RiskLevel


class AuditEvent(BaseModel):
    """审计事件领域组件。

    Attributes:
        event_id: 事件 ID。
        tenant_id: 租户 ID，用于数据隔离。
        action: 操作。
        resource_type: 资源类型。
        resource_id: 资源ID。
        risk_level: 风险级别。
        actor_type: 参与者类型。
        actor_id: 执行操作的参与者 ID。
        trace_id: 链路ID。
        payload: 事件、工作流或请求载荷。
        occurred_at: 用量发生时间。
    """

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
