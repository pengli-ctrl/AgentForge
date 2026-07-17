"""分布式追踪 — correlation_id 贯穿，span 管理器。

用于全链路可观测性（Layer 4 容错防线）。
通过 correlation_id 贯穿同一工作流的所有事件，
TraceContext 提供上下文管理器风格的 span 生命周期管理。

设计理念：
- correlation_id 在任务提交时生成，贯穿事件总线的所有事件
- 每个 Agent 执行创建一个 span，记录起止时间和元数据
- span 通过 parent_span_id 构建调用树
"""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from agentforge.storage.models.trace import TraceEvent, TraceSpan
from agentforge.storage.trace_store import TraceStore

logger = logging.getLogger(__name__)


@dataclass
class TraceContext:
    """Trace 上下文 — 在 Agent 执行期间携带的追踪信息。

    通过 contextvars 在异步调用链中传递，确保 correlation_id
    和 span_id 自动贯穿整个调用链。

    Attributes:
        trace_id: Trace ID（同一工作流共享）。
        span_id: 当前 Span ID。
        parent_span_id: 父 Span ID。
        correlation_id: 工作流关联 ID。
    """

    trace_id: str = ""
    span_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    parent_span_id: str = ""
    correlation_id: str = ""

    def __post_init__(self) -> None:
        """确保 trace_id 和 correlation_id 非空。"""
        if not self.trace_id:
            self.trace_id = self.correlation_id or str(uuid.uuid4())
        if not self.correlation_id:
            self.correlation_id = self.trace_id

    def to_dict(self) -> dict[str, str]:
        """转换为字典。

        Returns:
            包含 trace_id、span_id、parent_span_id、correlation_id 的字典。
        """
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "correlation_id": self.correlation_id,
        }


class TracingManager:
    """分布式追踪管理器 — span 生命周期管理。

    提供 context manager 风格的 span 创建和管理。
    每个 span 自动记录起止时间，完成后持久化到 TraceStore。

    Args:
        trace_store: Trace 数据存储实例。
    """

    def __init__(self, trace_store: TraceStore | None = None) -> None:
        self.trace_store = trace_store
        self._spans: dict[str, TraceSpan] = {}

    @asynccontextmanager
    async def start_span(
        self,
        agent_name: str,
        trace_id: str = "",
        parent_span_id: str = "",
        correlation_id: str = "",
    ) -> AsyncIterator[TraceSpan]:
        """启动一个新 span（async context manager）。

        用法：
            async with tracing_manager.start_span("code-review", trace_id=...) as span:
                span.add_event(event)
                # Agent 执行逻辑
                span.tool_calls += 1

        Args:
            agent_name: Agent 名称。
            trace_id: Trace ID（不传则自动生成）。
            parent_span_id: 父 Span ID。
            correlation_id: 关联 ID。

        Yields:
            TraceSpan 实例。
        """
        span = TraceSpan(
            span_id=str(uuid.uuid4()),
            trace_id=trace_id or correlation_id or str(uuid.uuid4()),
            parent_span_id=parent_span_id,
            agent_name=agent_name,
            start_time=time.time(),
        )

        self._spans[span.span_id] = span
        logger.debug(
            "Span started (agent=%s, trace_id=%s, span_id=%s)",
            agent_name,
            span.trace_id,
            span.span_id,
        )

        try:
            yield span
            span.status = "success"
        except Exception as e:
            span.status = "error"
            logger.error(
                "Span failed (agent=%s, error=%s)",
                agent_name,
                e,
                exc_info=True,
            )
            raise
        finally:
            span.finish()
            if self.trace_store:
                await self.trace_store.save_span(span)

            logger.debug(
                "Span finished (agent=%s, duration_ms=%.1f, status=%s)",
                agent_name,
                span.duration_ms,
                span.status,
            )
            self._spans.pop(span.span_id, None)

    async def record_event(
        self,
        span: TraceSpan,
        event_type: str,
        source_agent: str = "",
        target_agent: str = "",
        duration_ms: float = 0.0,
        status: str = "success",
        error_message: str = "",
        payload_summary: str = "",
    ) -> TraceEvent:
        """在 span 中记录一个事件。

        Args:
            span: 所属的 TraceSpan。
            event_type: 事件类型。
            source_agent: 事件来源 Agent。
            target_agent: 事件目标 Agent。
            duration_ms: 事件处理耗时（毫秒）。
            status: 事件状态（success/error/timeout）。
            error_message: 错误信息。
            payload_summary: 负载摘要。

        Returns:
            创建的 TraceEvent。
        """
        event = TraceEvent(
            trace_id=span.trace_id,
            span_id=span.span_id,
            parent_span_id=span.parent_span_id,
            event_type=event_type,
            source_agent=source_agent,
            target_agent=target_agent,
            timestamp=time.time(),
            duration_ms=duration_ms,
            status=status,
            error_message=error_message,
            payload_summary=payload_summary,
        )
        span.add_event(event)

        if self.trace_store:
            await self.trace_store.save_event(event)

        return event

    def get_current_span(self, span_id: str) -> TraceSpan | None:
        """获取当前活跃的 span。

        Args:
            span_id: Span ID。

        Returns:
            TraceSpan 实例，不存在则返回 None。
        """
        return self._spans.get(span_id)

    async def get_trace_summary(self, trace_id: str) -> dict[str, Any]:
        """获取 Trace 摘要。

        Args:
            trace_id: Trace ID。

        Returns:
            Trace 摘要字典。
        """
        if self.trace_store:
            return await self.trace_store.get_trace_summary(trace_id)
        return {"trace_id": trace_id, "event_count": 0, "span_count": 0}
