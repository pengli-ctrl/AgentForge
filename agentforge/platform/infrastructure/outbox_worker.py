"""AgentForge 平台基础设施层：outbox_worker。

本模块负责 outbox_worker 相关的平台能力，是 平台基础设施层 的组成部分。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：OutboxWorker。
"""

from __future__ import annotations

import asyncio

from agentforge.platform.infrastructure.outbox_dispatcher import OutboxDispatcher


class OutboxWorker:
    """OutboxWorker。

    OutboxWorker 封装相关领域行为，保持职责单一并降低调用方复杂度。

    主要成员：
    - 方法 dispatch_once()。
    - 方法 run_forever()。
    - 方法 stop()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    def __init__(self, dispatcher: OutboxDispatcher, interval_seconds: float = 1.0) -> None:
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Args:
            dispatcher: OutboxDispatcher，调用方传入的 dispatcher 参数。
            interval_seconds: float，调用方传入的 interval_seconds 参数。

        Returns:
            None，函数执行后的结果。
        """
        self._dispatcher = dispatcher
        self._interval_seconds = interval_seconds
        self._stopping = asyncio.Event()

    async def dispatch_once(self, limit: int = 100) -> int:
        """执行 dispatch_once 对应的逻辑，并返回处理结果。

        Args:
            limit: int，调用方传入的 limit 参数。

        Returns:
            int，函数执行后的结果。
        """
        return await self._dispatcher.dispatch_once(limit=limit)

    async def run_forever(self) -> None:
        """执行完整流程，并返回调用方需要的结果。

        Returns:
            None，函数执行后的结果。
        """
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
        """执行 stop 对应的核心操作，并保持调用契约稳定。

        Returns:
            None，函数执行后的结果。
        """
        self._stopping.set()
