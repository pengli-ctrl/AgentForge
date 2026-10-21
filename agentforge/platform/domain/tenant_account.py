"""租户账户模块。"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class TenantStatus(str, Enum):
    """租户状态枚举。"""

    PROVISIONING = "provisioning"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    CANCELLED = "cancelled"


class TenantAccount(BaseModel):
    """租户账户领域组件。

    Attributes:
        tenant_id: 租户 ID，用于数据隔离。
        name: 名称。
        plan_name: 套餐名称。
        status: 当前状态。
        created_at: 创建时间。
        updated_at: 更新时间。
        suspended_at: 于。
        cancelled_at: 于。
        status_reason: 状态原因。
    """

    model_config = ConfigDict(extra="forbid")

    tenant_id: str
    name: str
    plan_name: str
    status: TenantStatus = TenantStatus.PROVISIONING
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    suspended_at: datetime | None = None
    cancelled_at: datetime | None = None
    status_reason: str = ""


__all__ = ["TenantAccount", "TenantStatus"]
