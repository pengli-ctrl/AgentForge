"""
事件类型定义 — 事件驱动架构的基础数据结构。

所有 Agent 通过事件总线通信，事件携带 correlation_id（同一工作流共享）
和 context_snapshot（上下文快照 — 状态隔离的关键）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class EventType(str, Enum):
    """事件类型枚举 — 定义事件总线上流转的所有事件类型。

    事件类型遵循命名约定：{来源}_{动作}，如 AGENT_COMPLETED、TASK_SUBMITTED。
    """

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
    """Agent 间通信的标准事件格式。

    事件驱动架构的核心数据结构。每个事件携带：
    - correlation_id: 同一工作流共享，用于 trace 链路追踪
    - context_snapshot: 上下文快照，实现 Agent 间状态隔离
    - payload: 事件负载，包含具体的业务数据

    Attributes:
        event_type: 事件类型。
        source_agent: 事件来源 Agent 名称。
        payload: 事件负载，包含任务数据和结果。
        correlation_id: 关联 ID，同一工作流内的所有事件共享。
        context_snapshot: 上下文快照，冻结发送时刻的上下文副本。
        target_agent: 目标 Agent 名称（可选，用于定向路由）。
        timestamp: 事件创建时间戳。
    """

    event_type: EventType
    source_agent: str
    payload: dict[str, Any] = field(default_factory=dict)
    correlation_id: str = ""
    context_snapshot: dict[str, Any] = field(default_factory=dict)
    target_agent: Optional[str] = None
    timestamp: float = field(default_factory=lambda: __import__("time").time())

    def __post_init__(self) -> None:
        """确保 correlation_id 非空。"""
        if not self.correlation_id:
            self.correlation_id = f"{self.source_agent}-{self.timestamp}"


@dataclass
class BatchEvent:
    """批量事件 — 脉冲整形器将多个统计趋同的并发事件合并为单个批量事件。

    用于解决并发同步脉冲故障模式：多个独立任务的子任务完成时间
    在统计上趋同时，合并为批量事件避免下游 Agent 过载。

    Attributes:
        correlation_id: 关联 ID。
        target_agent: 目标 Agent 名称。
        sub_events: 合并的子事件列表。
        batch_size: 批量大小。
    """

    correlation_id: str
    target_agent: str
    sub_events: list[AgentEvent] = field(default_factory=list)
    batch_size: int = 0

    def __post_init__(self) -> None:
        if self.batch_size == 0:
            self.batch_size = len(self.sub_events)
