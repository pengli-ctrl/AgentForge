"""AgentForge 平台领域模型层：events。

本模块定义 events 领域模型，约束业务状态、输入输出结构和跨层数据契约。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：EventEnvelope。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EventEnvelope(BaseModel):
    """EventEnvelope。

    EventEnvelope 是结构化数据模型，负责承载输入、输出或持久化数据，并执行字段级校验。

    主要成员：
    - model_config: ConfigDict(extra='forbid')。
    - event_id: str。
    - event_type: str。
    - event_version: int。
    - tenant_id: str。
    - task_id: str。
    - trace_id: str。
    - producer: str。
    - occurred_at: datetime。
    - payload: dict[str, Any]。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    model_config = ConfigDict(extra="forbid")

    event_id: str
    event_type: str
    event_version: int = 1
    tenant_id: str
    task_id: str
    trace_id: str
    producer: str
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    payload: dict[str, Any] = Field(default_factory=dict)
