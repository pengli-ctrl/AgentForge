"""Outbox工作进程模块。"""

from __future__ import annotations

import asyncio

from agentforge.platform.infrastructure.outbox_dispatcher import OutboxDispatcher


class OutboxWorker:
    """Outbox工作进程相关组件。"""

    def __init__(self, dispatcher: OutboxDispatcher, interval_seconds: float = 1.0) -> None:
        """初始化 OutboxWorker。

        Args:
            dispatcher: 调度器。
            interval_seconds: 输入参数。
        """
        self._dispatcher = dispatcher
        self._interval_seconds = interval_seconds
        self._stopping = asyncio.Event()

    async def dispatch_once(self, limit: int = 100) -> int:
        """分发一次。

        Args:
            limit: 返回记录的最大数量。

        Returns:
            整数结果。
        """
        return await self._dispatcher.dispatch_once(limit=limit)

    async def run_forever(self) -> None:
        """运行Outbox工作进程。"""
        publisher = getattr(self._dispatcher, "_publisher", None)
        if publisher is not None and hasattr(publisher, "start"):
            await publisher.start()
        try:
            while not self._stopping.is_set():
                await self.dispatch_once()
                try:
                    await asyncio.wait_for(self._stopping.wait(), timeout=self._interval_seconds)
                except asyncio.TimeoutError:
                    continue
        finally:
            if publisher is not None and hasattr(publisher, "stop"):
                await publisher.stop()

    def stop(self) -> None:
        """停止Outbox工作进程。"""
        self._stopping.set()
