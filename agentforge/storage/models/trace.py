"""链路模块。"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TraceEvent:
    """链路事件领域组件。

    Attributes:
        event_id: 事件 ID。
        trace_id: 链路ID。
        span_id: 链路片段ID。
        parent_span_id: 链路片段ID。
        event_type: 事件。
        source_agent: 来源智能体。
        target_agent: 目标智能体。
        timestamp: 字段值。
        duration_ms: 持续时间毫秒。
        payload_summary: 载荷摘要。
        status: 当前状态。
        error_message: 错误。
    """

    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    trace_id: str = ""
    span_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    parent_span_id: str = ""
    event_type: str = ""
    source_agent: str = ""
    target_agent: str = ""
    timestamp: float = field(default_factory=time.time)
    duration_ms: float = 0.0
    payload_summary: str = ""
    status: str = "success"
    error_message: str = ""

    def to_dict(self) -> dict[str, Any]:
        """处理到字典。

        Returns:
            结构化结果字典。
        """
        return {
            "event_id": self.event_id,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "event_type": self.event_type,
            "source_agent": self.source_agent,
            "target_agent": self.target_agent,
            "timestamp": self.timestamp,
            "duration_ms": self.duration_ms,
            "payload_summary": self.payload_summary,
            "status": self.status,
            "error_message": self.error_message,
        }


@dataclass
class TraceSpan:
    """链路片段相关组件。

    Attributes:
        span_id: 链路片段ID。
        trace_id: 链路ID。
        parent_span_id: 链路片段ID。
        agent_name: 智能体名称。
        start_time: 开始。
        end_time: 结束。
        duration_ms: 持续时间毫秒。
        tool_calls: 工具调用。
        llm_calls: LLM调用。
        status: 当前状态。
        events: 事件。
    """

    span_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    trace_id: str = ""
    parent_span_id: str = ""
    agent_name: str = ""
    start_time: float = field(default_factory=time.time)
    end_time: float = 0.0
    duration_ms: float = 0.0
    tool_calls: int = 0
    llm_calls: int = 0
    status: str = "success"
    events: list[TraceEvent] = field(default_factory=list)

    def finish(self) -> None:
        """结束链路记录并写入完成状态。"""
        self.end_time = time.time()
        self.duration_ms = (self.end_time - self.start_time) * 1000

    def add_event(self, event: TraceEvent) -> None:
        """保存事件。

        Args:
            event: 待处理事件。
        """
        event.span_id = self.span_id
        event.trace_id = self.trace_id
        self.events.append(event)

    def to_dict(self) -> dict[str, Any]:
        """处理到字典。

        Returns:
            结构化结果字典。
        """
        return {
            "span_id": self.span_id,
            "trace_id": self.trace_id,
            "parent_span_id": self.parent_span_id,
            "agent_name": self.agent_name,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": self.duration_ms,
            "tool_calls": self.tool_calls,
            "llm_calls": self.llm_calls,
            "status": self.status,
            "events": [e.to_dict() for e in self.events],
        }
