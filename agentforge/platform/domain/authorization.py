"""授权模块。"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class AuthorizationOutcome(str, Enum):
    """授权决策结果枚举。"""

    ALLOWED = "allowed"
    DENIED = "denied"
    REQUIRES_APPROVAL = "requires_approval"


class AuthorizationDecision(BaseModel):
    """授权决策领域组件。

    Attributes:
        authorization_id: 授权ID。
        tenant_id: 租户 ID，用于数据隔离。
        action: 操作。
        resource_type: 资源类型。
        resource_id: 资源ID。
        principal: 字段值。
        outcome: 结果。
        reasons: 字段值。
        approval_ref: 审批引用。
        decided_at: 于。
    """

    model_config = ConfigDict(extra="forbid")

    authorization_id: str
    tenant_id: str
    action: str
    resource_type: str
    resource_id: str
    principal: str
    outcome: AuthorizationOutcome
    reasons: list[str] = Field(default_factory=list)
    approval_ref: str | None = None
    decided_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
