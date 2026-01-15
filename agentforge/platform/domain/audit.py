"""AgentForge 平台领域模型层：audit。

本模块定义 audit 领域模型，约束业务状态、输入输出结构和跨层数据契约。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：AuditEvent。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from agentforge.platform.domain.ticket import RiskLevel


class AuditEvent(BaseModel):
    """AuditEvent。

    AuditEvent 是结构化数据模型，负责承载输入、输出或持久化数据，并执行字段级校验。

    主要成员：
    - model_config: ConfigDict(extra='forbid')。
    - event_id: str。
    - tenant_id: str。
    - action: str。
    - resource_type: str。
    - resource_id: str。
    - risk_level: RiskLevel。
    - actor_type: str。
    - actor_id: str。
    - trace_id: str | None。
    - payload: dict[str, Any]。
    - occurred_at: datetime。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
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
