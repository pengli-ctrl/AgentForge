"""
脉冲整形器 — 将统计趋同的并发事件平滑为稳定流量。

解决并发同步脉冲故障模式：
多个独立任务的子任务完成时间在统计上趋同时，
会产生周期性的负载脉冲（Pulse Synchronization）。

这不是"突发流量"问题 — 没有外部流量尖峰，每个任务都在正常执行。
问题的本质是多个独立随机过程的统计趋同（中心极限定理）。

容错方案：水位线对齐 + 自适应批量合并
- 事件不立即发送，进入对齐窗口
- 达到批量上限 → 立即 flush
- 否则启动/重置窗口定时器
- 合并为单个批量事件，下游只处理一次

与 TCP 的类比：这个方案本质上是 TCP Nagle 算法 + 延迟确认（Delayed ACK）
在多 Agent 事件总线上的应用。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from agentforge.core.event_types import AgentEvent, BatchEvent, EventType

logger = logging.getLogger(__name__)


class PulseShaper:
    """脉冲整形器 — 将统计趋同的并发事件平滑为稳定流量。

    事件总线不只是"传递事件"，还要"整形流量"。脉冲同步是统计必然，
    不能靠限制并发来消除（那会降低吞吐量），只能靠缓冲和合并来平滑。

    工作流程：
    1. 事件到达后不立即发送，进入对齐窗口缓冲
    2. 达到批量上限 → 立即 flush，不等窗口
    3. 否则启动/重置窗口定时器
    4. 窗口超时 → flush 缓冲区中的所有事件
    5. 合并为单个 BatchEvent，下游只处理一次

    Args:
        window_seconds: 对齐窗口大小（秒），窗口内的事件合并发送。
        max_batch_size: 单批最大事件数。
    """

    def __init__(
        self,
        window_seconds: float = 5.0,
        max_batch_size: int = 10,
    ) -> None:
        self.window = window_seconds  # 对齐窗口：窗口内的事件合并发送
        self.max_batch = max_batch_size  # 单批最大事件数
        self.pending: list[AgentEvent] = []  # 待发送事件缓冲
        self.flush_task: asyncio.Task | None = None

    async def on_event(self, event: AgentEvent, bus: Any) -> None:
        """事件不立即发送，进入对齐窗口。

        Args:
            event: 接收到的 Agent 事件。
            bus: 事件总线实例，用于发送合并后的批量事件。
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
        """延迟 flush — 等待窗口超时后发送缓冲区中的事件。

        Args:
            bus: 事件总线实例。
        """
        await asyncio.sleep(self.window)
        await self._flush(bus)

    async def _flush(self, bus: Any) -> None:
        """将缓冲区中的事件合并为批量事件并发送。

        合并为单个 BatchEvent，下游只处理一次，
        避免 60 个并发事件在 30 秒内涌入下游 Agent 导致过载。

        Args:
            bus: 事件总线实例。
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
