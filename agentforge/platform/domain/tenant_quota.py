"""租户配额模块。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TenantQuota(BaseModel):
    """租户配额领域组件。

    Attributes:
        tenant_id: 租户 ID，用于数据隔离。
        monthly_limit: 月度限制。
        warning_threshold: 警告阈值。
        hard_limit: 硬限制。
        enabled: 是否启用。
        updated_at: 更新时间。
    """

    model_config = ConfigDict(extra="forbid")

    tenant_id: str
    monthly_limit: float = 0.0
    warning_threshold: float = 0.8
    hard_limit: float = 1.0
    enabled: bool = True
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def usage_status(self, used: float) -> dict[str, Any]:
        """处理用量状态。

        Args:
            used: 已使用。

        Returns:
            结构化结果字典。
        """
        if not self.enabled or self.monthly_limit <= 0:
            return {"status": "active", "used": used, "limit": self.monthly_limit}
        ratio = used / self.monthly_limit
        if ratio >= self.hard_limit:
            status = "blocked"
        elif ratio >= self.warning_threshold:
            status = "warning"
        else:
            status = "active"
        return {
            "status": status,
            "used": used,
            "limit": self.monthly_limit,
            "ratio": round(ratio, 4),
        }
