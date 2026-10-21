"""Outbox调度器模块。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping

from agentforge.platform.application.ports import EventPublisher
from agentforge.platform.domain.events import EventEnvelope
from agentforge.platform.infrastructure.outbox_store import SQLAlchemyOutboxStore


class OutboxDispatcher:
    """Outbox调度器相关组件。"""

    def __init__(
        self,
        store: SQLAlchemyOutboxStore,
        publisher: EventPublisher,
        event_handlers: Mapping[str, Callable[[EventEnvelope], Awaitable[None]]] | None = None,
    ) -> None:
        """初始化 OutboxDispatcher。

        Args:
            store: 状态存储实例。
            publisher: 发布器。
            event_handlers: 事件。
        """
        self._store = store
        self._publisher = publisher
        self._event_handlers = dict(event_handlers or {})

    async def dispatch_once(self, limit: int = 100) -> int:
        """分发一次。

        Args:
            limit: 返回记录的最大数量。

        Returns:
            整数结果。
        """
        events = await self._store.fetch_pending(limit=limit)
        published = 0
        for event in events:
            handler = self._event_handlers.get(event.event_type)
            handler_name = _handler_name(handler)
            claimed_here = False
            try:
                if handler is not None:
                    claim = await self._store.claim_handler(event.event_id, handler_name)
                    if claim == "busy":
                        continue
                    if claim == "claimed":
                        claimed_here = True
                        await handler(event)
                        await self._store.complete_handler(event.event_id, handler_name)
                await self._publisher.publish(event)
                await self._store.mark_published(event.event_id)
                published += 1
            except Exception as exc:
                if claimed_here and handler is not None:
                    await self._store.release_handler(
                        event.event_id,
                        handler_name,
                        error=str(exc),
                    )
                await self._store.mark_failed(event.event_id, str(exc))
        return published


def _handler_name(handler: Callable[[EventEnvelope], Awaitable[None]] | None) -> str:
    """处理器名称。

    Args:
        handler: 处理器。

    Returns:
        字符串结果。
    """
    if handler is None:
        return ""
    module = getattr(handler, "__module__", "unknown")
    qualname = getattr(handler, "__qualname__", "handler")
    return f"{module}.{qualname}"
