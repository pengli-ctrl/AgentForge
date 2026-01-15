"""AgentForge 平台基础设施层：outbox_dispatcher。

本模块负责 outbox_dispatcher 相关的平台能力，是 平台基础设施层 的组成部分。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：OutboxDispatcher。
"""

from __future__ import annotations

from agentforge.platform.application.ports import EventPublisher
from agentforge.platform.infrastructure.outbox_store import SQLAlchemyOutboxStore


class OutboxDispatcher:
    """OutboxDispatcher。

    OutboxDispatcher 封装相关领域行为，保持职责单一并降低调用方复杂度。

    主要成员：
    - 方法 dispatch_once()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    def __init__(self, store: SQLAlchemyOutboxStore, publisher: EventPublisher) -> None:
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Args:
            store: SQLAlchemyOutboxStore，调用方传入的 store 参数。
            publisher: EventPublisher，调用方传入的 publisher 参数。

        Returns:
            None，函数执行后的结果。
        """
        self._store = store
        self._publisher = publisher

    async def dispatch_once(self, limit: int = 100) -> int:
        """执行 dispatch_once 对应的逻辑，并返回处理结果。

        Args:
            limit: int，调用方传入的 limit 参数。

        Returns:
            int，函数执行后的结果。
        """
        events = await self._store.fetch_pending(limit=limit)
        published = 0
        for event in events:
            try:
                await self._publisher.publish(event)
                await self._store.mark_published(event.event_id)
                published += 1
            except Exception as exc:
                await self._store.mark_failed(event.event_id, str(exc))
        return published
