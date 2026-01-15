"""AgentForge 平台领域模型层：tenant_quota。

本模块定义 tenant_quota 领域模型，约束业务状态、输入输出结构和跨层数据契约。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：TenantQuota。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TenantQuota(BaseModel):
    """TenantQuota。

    TenantQuota 是结构化数据模型，负责承载输入、输出或持久化数据，并执行字段级校验。

    主要成员：
    - model_config: ConfigDict(extra='forbid')。
    - tenant_id: str。
    - monthly_limit: float。
    - warning_threshold: float。
    - hard_limit: float。
    - enabled: bool。
    - updated_at: datetime。
    - 方法 usage_status()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    model_config = ConfigDict(extra="forbid")

    tenant_id: str
    monthly_limit: float = 0.0
    warning_threshold: float = 0.8
    hard_limit: float = 1.0
    enabled: bool = True
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def usage_status(self, used: float) -> dict[str, Any]:
        """执行 usage_status 对应的逻辑，并返回处理结果。

        Args:
            used: float，调用方传入的 used 参数。

        Returns:
            dict[str, Any]，函数执行后的结果。
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
