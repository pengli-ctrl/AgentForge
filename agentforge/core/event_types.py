"""事件模块。"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class EventType(str, Enum):
    """事件类型枚举 — 定义事件总线上流转的所有事件类型。"""

    # 任务生命周期
    TASK_SUBMITTED = "task_submitted"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"

    # Agent 生命周期
    AGENT_STARTED = "agent_started"
    AGENT_COMPLETED = "agent_completed"
    AGENT_FAILED = "agent_failed"

    # 工具执行
    TOOL_CALLED = "tool_called"
    TOOL_COMPLETED = "tool_completed"

    # 编排控制
    ROUTE_DECISION = "route_decision"
    CONFLICT_ESCALATED = "conflict_escalated"

    # 子任务（动态路由中的子步骤）
    SUBTASK_COMPLETED = "subtask_completed"

    # 批量事件（脉冲整形器输出）
    BATCH_EVENT = "batch_event"

    # 容错相关
    CIRCUIT_BREAKER_OPEN = "circuit_breaker_open"
    RETRY_EXHAUSTED = "retry_exhausted"


@dataclass
class AgentEvent:
    """智能体事件领域组件。

    Attributes:
        event_type: 事件。
        source_agent: 来源智能体。
        payload: 事件、工作流或请求载荷。
        correlation_id: 用于关联同一业务链路的关联 ID。
        context_snapshot: 上下文快照。
        target_agent: 目标智能体。
        timestamp: 字段值。
    """

    event_type: EventType
    source_agent: str
    payload: dict[str, Any] = field(default_factory=dict)
    correlation_id: str = ""
    context_snapshot: dict[str, Any] = field(default_factory=dict)
    target_agent: Optional[str] = None
    timestamp: float = field(default_factory=lambda: __import__("time").time())

    def __post_init__(self) -> None:
        """校验并补全初始化后的字段。"""
        if not self.correlation_id:
            self.correlation_id = f"{self.source_agent}-{self.timestamp}"


@dataclass
class BatchEvent:
    """批量事件 — 脉冲整形器将多个统计趋同的并发事件合并为单个批量事件。

    Attributes:
        correlation_id: 用于关联同一业务链路的关联 ID。
        target_agent: 目标智能体。
        sub_events: 事件。
        batch_size: 批次大小。
    """

    correlation_id: str
    target_agent: str
    sub_events: list[AgentEvent] = field(default_factory=list)
    batch_size: int = 0

    def __post_init__(self) -> None:
        """校验并补全初始化后的字段。"""
        if self.batch_size == 0:
            self.batch_size = len(self.sub_events)
