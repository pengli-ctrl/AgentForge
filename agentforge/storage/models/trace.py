"""Trace 数据模型 — 分布式追踪的数据结构定义。

Trace 数据记录每个事件在事件总线上的完整链路，
用于全链路可观测性（Layer 4 容错防线）。

每个 Trace 包含多个 TraceEvent，通过 correlation_id 关联。
每个 TraceEvent 记录单个事件的处理过程。
TraceSpan 表示一个 Agent 的执行跨度（从 AGENT_STARTED 到 AGENT_COMPLETED）。
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TraceEvent:
    """Trace 事件 — 记录事件总线上单个事件的处理过程。

    每个事件从发布到被订阅者处理完成，记录为一个 TraceEvent。
    通过 correlation_id 关联同一工作流的所有事件。

    Attributes:
        event_id: 事件唯一标识（UUID）。
        trace_id: Trace ID（同一工作流共享）。
        span_id: Span ID（同一 Agent 的执行跨度内共享）。
        parent_span_id: 父 Span ID（用于构建调用树）。
        event_type: 事件类型（如 agent_completed）。
        source_agent: 事件来源 Agent 名称。
        target_agent: 事件目标 Agent 名称。
        timestamp: 事件时间戳。
        duration_ms: 事件处理耗时（毫秒）。
        payload_summary: 事件负载摘要（避免存储完整负载）。
        status: 事件处理状态（success / error / timeout）。
        error_message: 错误信息（status 为 error 时填充）。
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
        """将 TraceEvent 序列化为字典。

        Returns:
            包含所有字段的字典。
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
    """Trace Span — 一个 Agent 的执行跨度。

    从 AGENT_STARTED 到 AGENT_COMPLETED（或 AGENT_FAILED）为一个 Span。
    Span 包含起止时间、执行耗时、工具调用次数等统计信息。

    Attributes:
        span_id: Span 唯一标识。
        trace_id: 所属 Trace 的 ID。
        parent_span_id: 父 Span ID（触发此 Agent 的上游 Span）。
        agent_name: Agent 名称。
        start_time: Span 开始时间戳。
        end_time: Span 结束时间戳。
        duration_ms: Span 总耗时（毫秒）。
        tool_calls: 工具调用次数。
        llm_calls: LLM 调用次数。
        status: Span 状态（success / error / timeout）。
        events: Span 内的 TraceEvent 列表。
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
        """结束 Span，计算耗时。"""
        self.end_time = time.time()
        self.duration_ms = (self.end_time - self.start_time) * 1000

    def add_event(self, event: TraceEvent) -> None:
        """向 Span 添加事件。

        Args:
            event: 要添加的 TraceEvent。
        """
        event.span_id = self.span_id
        event.trace_id = self.trace_id
        self.events.append(event)

    def to_dict(self) -> dict[str, Any]:
        """将 TraceSpan 序列化为字典。

        Returns:
            包含所有字段的字典。
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
