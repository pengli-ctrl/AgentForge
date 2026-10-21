"""链路存储模块。"""

from __future__ import annotations

import logging
from typing import Any

from agentforge.storage.models.trace import TraceEvent, TraceSpan

logger = logging.getLogger(__name__)


class TraceStore:
    """链路领域组件。"""

    def __init__(self, db_pool: Any = None) -> None:
        """初始化 TraceStore。

        Args:
            db_pool: 数据库。
        """
        self.db_pool = db_pool
        self._events: list[TraceEvent] = []
        self._spans: list[TraceSpan] = []

    async def save_event(self, event: TraceEvent) -> None:
        """保存事件。

        Args:
            event: 待处理事件。
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
        """保存链路段。

        Args:
            span: 链路片段对象。
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
        """获取链路事件。

        Args:
            trace_id: 链路追踪 ID。

        Returns:
            结果列表。
        """
        if self.db_pool:
            return await self._db_get_events(trace_id)

        events = [e for e in self._events if e.trace_id == trace_id]
        events.sort(key=lambda e: e.timestamp)
        return events

    async def get_trace_spans(self, trace_id: str) -> list[TraceSpan]:
        """获取链路。

        Args:
            trace_id: 链路追踪 ID。

        Returns:
            结果列表。
        """
        if self.db_pool:
            return await self._db_get_spans(trace_id)

        spans = [s for s in self._spans if s.trace_id == trace_id]
        spans.sort(key=lambda s: s.start_time)
        return spans

    async def get_trace_summary(self, trace_id: str) -> dict[str, Any]:
        """读取链路摘要。

        Args:
            trace_id: 链路追踪 ID。

        Returns:
            结构化结果字典。
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
        """清理链路。

        Args:
            trace_id: 链路追踪 ID。
        """
        if self.db_pool:
            await self._db_cleanup(trace_id)
        else:
            self._events = [e for e in self._events if e.trace_id != trace_id]
            self._spans = [s for s in self._spans if s.trace_id != trace_id]

    # --- MySQL 后端方法 ---

    async def _db_save_event(self, event: TraceEvent) -> None:
        """处理数据库保存事件。

        Args:
            event: 待处理事件。
        """
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
        """处理数据库保存链路片段。

        Args:
            span: 链路片段对象。
        """
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
        """处理数据库获取事件。

        Args:
            trace_id: 链路追踪 ID。

        Returns:
            结果列表。
        """
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetchall(
                "SELECT * FROM trace_events WHERE trace_id = %s " "ORDER BY timestamp ASC",
                (trace_id,),
            )
            return [_row_to_event(row) for row in rows]

    async def _db_get_spans(self, trace_id: str) -> list[TraceSpan]:
        """处理数据库获取。

        Args:
            trace_id: 链路追踪 ID。

        Returns:
            结果列表。
        """
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetchall(
                "SELECT * FROM trace_spans WHERE trace_id = %s " "ORDER BY start_time ASC",
                (trace_id,),
            )
            return [_row_to_span(row) for row in rows]

    async def _db_cleanup(self, trace_id: str) -> None:
        """处理数据库清理。

        Args:
            trace_id: 链路追踪 ID。
        """
        async with self.db_pool.acquire() as conn:
            await conn.execute("DELETE FROM trace_events WHERE trace_id = %s", (trace_id,))
            await conn.execute("DELETE FROM trace_spans WHERE trace_id = %s", (trace_id,))


def _row_to_event(row: Any) -> TraceEvent:
    """处理记录到事件。

    Args:
        row: 记录。

    Returns:
        链路事件结果。
    """
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
    """处理记录到链路片段。

    Args:
        row: 记录。

    Returns:
        链路链路片段结果。
    """
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
