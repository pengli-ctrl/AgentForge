"""事件模块。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EventEnvelope(BaseModel):
    """事件相关组件。

    Attributes:
        event_id: 事件 ID。
        event_type: 事件。
        event_version: 事件版本。
        tenant_id: 租户 ID，用于数据隔离。
        task_id: 任务ID。
        trace_id: 链路ID。
        producer: 字段值。
        occurred_at: 用量发生时间。
        payload: 事件、工作流或请求载荷。
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
