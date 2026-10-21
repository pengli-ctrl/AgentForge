"""脉冲整形器模块。"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from agentforge.core.event_types import AgentEvent, BatchEvent, EventType

logger = logging.getLogger(__name__)


class PulseShaper:
    """脉冲整形器 — 将统计趋同的并发事件平滑为稳定流量。"""

    def __init__(
        self,
        window_seconds: float = 5.0,
        max_batch_size: int = 10,
    ) -> None:
        """初始化 PulseShaper。

        Args:
            window_seconds: 窗口。
            max_batch_size: 最大批次大小。
        """
        self.window = window_seconds  # 对齐窗口：窗口内的事件合并发送
        self.max_batch = max_batch_size  # 单批最大事件数
        self.pending: list[AgentEvent] = []  # 待发送事件缓冲
        self.flush_task: asyncio.Task | None = None

    async def on_event(self, event: AgentEvent, bus: Any) -> None:
        """事件不立即发送，进入对齐窗口。

        Args:
            event: 待处理事件。
            bus: 输入参数。
        """
        self.pending.append(event)

        # 达到批量上限 → 立即 flush，不等窗口
        if len(self.pending) >= self.max_batch:
            await self._flush(bus)
            return

        # 否则启动/重置窗口定时器
        if self.flush_task is None:
            self.flush_task = asyncio.create_task(self._delayed_flush(bus))

    async def _delayed_flush(self, bus: Any) -> None:
        """处理延迟刷新。

        Args:
            bus: 输入参数。
        """
        await asyncio.sleep(self.window)
        await self._flush(bus)

    async def _flush(self, bus: Any) -> None:
        """将缓冲区中的事件合并为批量事件并发送。

        Args:
            bus: 输入参数。
        """
        if not self.pending:
            return

        batch = self.pending.copy()
        self.pending.clear()
        self.flush_task = None

        # 合并为单个批量事件，下游只处理一次
        merged = BatchEvent(
            correlation_id=batch[0].correlation_id,
            target_agent=batch[0].target_agent or "result-aggregator",
            sub_events=batch,
            batch_size=len(batch),
        )

        logger.info(
            "PulseShaper flushed (batch_size=%d, correlation_id=%s)",
            len(batch),
            batch[0].correlation_id,
        )

        # 通过事件总线发送批量事件
        batch_event = AgentEvent(
            event_type=EventType.BATCH_EVENT,
            source_agent="pulse-shaper",
            correlation_id=merged.correlation_id,
            target_agent=merged.target_agent,
            payload={
                "batch_size": merged.batch_size,
                "sub_events": [
                    {"source": e.source_agent, "payload": e.payload} for e in merged.sub_events
                ],
            },
        )
        await bus.publish(batch_event)
