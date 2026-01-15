"""AgentForge 任务存储层：trace_store。

本模块负责 trace_store 相关能力，是 任务存储层 的组成部分。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 涉及租户、任务、审计或成本的数据必须保持隔离和可追踪。
- 关键路径应保留日志、指标或链路追踪信息。
- 主要类：TraceStore。
"""

from __future__ import annotations

import logging
from typing import Any

from agentforge.storage.models.trace import TraceEvent, TraceSpan

logger = logging.getLogger(__name__)


class TraceStore:
    """Trace 数据存储 — 记录和查询事件的完整链路。

    支持两种后端：
    - in-memory（默认）：使用列表存储，适合开发/测试
    - MySQL（生产环境）：通过数据库连接池操作

    Args:
        db_pool: 数据库连接池（可选，不传则使用内存存储）。
    """

    def __init__(self, db_pool: Any = None) -> None:
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Args:
            db_pool: Any，调用方传入的 db_pool 参数。

        Returns:
            None，函数执行后的结果。
        """
        self.db_pool = db_pool
        self._events: list[TraceEvent] = []
        self._spans: list[TraceSpan] = []

    async def save_event(self, event: TraceEvent) -> None:
        """保存一个 Trace 事件。

        Args:
            event: 要保存的 TraceEvent。
        """
        if self.db_pool:
            await self._db_save_event(event)
        else:
            self._events.append(event)

        logger.debug(
            "Trace event saved (trace_id=%s, event_type=%s, source=%s)",
            event.trace_id,
            event.event_type,
            event.source_agent,
        )

    async def save_span(self, span: TraceSpan) -> None:
        """保存一个 Trace Span。

        Args:
            span: 要保存的 TraceSpan。
        """
        if self.db_pool:
            await self._db_save_span(span)
        else:
            self._spans.append(span)

        logger.debug(
            "Trace span saved (trace_id=%s, agent=%s, duration_ms=%.1f)",
            span.trace_id,
            span.agent_name,
            span.duration_ms,
        )

    async def get_trace_events(self, trace_id: str) -> list[TraceEvent]:
        """查询指定 Trace 的所有事件。

        Args:
            trace_id: Trace ID。

        Returns:
            按时间排序的 TraceEvent 列表。
        """
        if self.db_pool:
            return await self._db_get_events(trace_id)

        events = [e for e in self._events if e.trace_id == trace_id]
        events.sort(key=lambda e: e.timestamp)
        return events

    async def get_trace_spans(self, trace_id: str) -> list[TraceSpan]:
        """查询指定 Trace 的所有 Span。

        Args:
            trace_id: Trace ID。

        Returns:
            按开始时间排序的 TraceSpan 列表。
        """
        if self.db_pool:
            return await self._db_get_spans(trace_id)

        spans = [s for s in self._spans if s.trace_id == trace_id]
        spans.sort(key=lambda s: s.start_time)
        return spans

    async def get_trace_summary(self, trace_id: str) -> dict[str, Any]:
        """获取 Trace 摘要信息。

        Args:
            trace_id: Trace ID。

        Returns:
            包含事件数、Span 数、总耗时、Agent 列表的摘要字典。
        """
        events = await self.get_trace_events(trace_id)
        spans = await self.get_trace_spans(trace_id)

        total_duration = sum(s.duration_ms for s in spans)
        agent_names = list({s.agent_name for s in spans if s.agent_name})
        error_count = sum(1 for e in events if e.status == "error")

        return {
            "trace_id": trace_id,
            "event_count": len(events),
            "span_count": len(spans),
            "total_duration_ms": total_duration,
            "agents": agent_names,
            "error_count": error_count,
            "has_errors": error_count > 0,
        }

    async def cleanup(self, trace_id: str) -> None:
        """清理指定 Trace 的所有数据。

        Args:
            trace_id: Trace ID。
        """
        if self.db_pool:
            await self._db_cleanup(trace_id)
        else:
            self._events = [e for e in self._events if e.trace_id != trace_id]
            self._spans = [s for s in self._spans if s.trace_id != trace_id]

    # --- MySQL 后端方法 ---

    async def _db_save_event(self, event: TraceEvent) -> None:
        """MySQL 后端：保存事件。"""
        d = event.to_dict()
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO trace_events (event_id, trace_id, span_id, "
                "parent_span_id, event_type, source_agent, target_agent, "
                "timestamp, duration_ms, payload_summary, status, error_message) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    d["event_id"],
                    d["trace_id"],
                    d["span_id"],
                    d["parent_span_id"],
                    d["event_type"],
                    d["source_agent"],
                    d["target_agent"],
                    d["timestamp"],
                    d["duration_ms"],
                    d["payload_summary"],
                    d["status"],
                    d["error_message"],
                ),
            )

    async def _db_save_span(self, span: TraceSpan) -> None:
        """MySQL 后端：保存 Span。"""
        d = span.to_dict()
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO trace_spans (span_id, trace_id, parent_span_id, "
                "agent_name, start_time, end_time, duration_ms, "
                "tool_calls, llm_calls, status) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    d["span_id"],
                    d["trace_id"],
                    d["parent_span_id"],
                    d["agent_name"],
                    d["start_time"],
                    d["end_time"],
                    d["duration_ms"],
                    d["tool_calls"],
                    d["llm_calls"],
                    d["status"],
                ),
            )

    async def _db_get_events(self, trace_id: str) -> list[TraceEvent]:
        """MySQL 后端：查询事件。"""
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetchall(
                "SELECT * FROM trace_events WHERE trace_id = %s " "ORDER BY timestamp ASC",
                (trace_id,),
            )
            return [_row_to_event(row) for row in rows]

    async def _db_get_spans(self, trace_id: str) -> list[TraceSpan]:
        """MySQL 后端：查询 Span。"""
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetchall(
                "SELECT * FROM trace_spans WHERE trace_id = %s " "ORDER BY start_time ASC",
                (trace_id,),
            )
            return [_row_to_span(row) for row in rows]

    async def _db_cleanup(self, trace_id: str) -> None:
        """MySQL 后端：清理 Trace 数据。"""
        async with self.db_pool.acquire() as conn:
            await conn.execute("DELETE FROM trace_events WHERE trace_id = %s", (trace_id,))
            await conn.execute("DELETE FROM trace_spans WHERE trace_id = %s", (trace_id,))


def _row_to_event(row: Any) -> TraceEvent:
    """将数据库行转换为 TraceEvent。"""
    data = dict(row) if isinstance(row, dict) else dict(row._asdict())
    return TraceEvent(
        event_id=data.get("event_id", ""),
        trace_id=data.get("trace_id", ""),
        span_id=data.get("span_id", ""),
        parent_span_id=data.get("parent_span_id", ""),
        event_type=data.get("event_type", ""),
        source_agent=data.get("source_agent", ""),
        target_agent=data.get("target_agent", ""),
        timestamp=data.get("timestamp", 0.0),
        duration_ms=data.get("duration_ms", 0.0),
        payload_summary=data.get("payload_summary", ""),
        status=data.get("status", "success"),
        error_message=data.get("error_message", ""),
    )


def _row_to_span(row: Any) -> TraceSpan:
    """将数据库行转换为 TraceSpan。"""
    data = dict(row) if isinstance(row, dict) else dict(row._asdict())
    return TraceSpan(
        span_id=data.get("span_id", ""),
        trace_id=data.get("trace_id", ""),
        parent_span_id=data.get("parent_span_id", ""),
        agent_name=data.get("agent_name", ""),
        start_time=data.get("start_time", 0.0),
        end_time=data.get("end_time", 0.0),
        duration_ms=data.get("duration_ms", 0.0),
        tool_calls=data.get("tool_calls", 0),
        llm_calls=data.get("llm_calls", 0),
        status=data.get("status", "success"),
    )
