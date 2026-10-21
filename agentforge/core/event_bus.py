"""事件模块。"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Any, Callable, Coroutine

from agentforge.core.event_types import AgentEvent, EventType

logger = logging.getLogger(__name__)

# 订阅者回调类型
SubscriberCallback = Callable[[AgentEvent], Coroutine[Any, Any, None]]


class EventBus:
    """进程内事件总线，负责事件发布与订阅。"""

    def __init__(
        self,
        backend: str = "redis",
        redis_url: str = "redis://localhost:6379",
        kafka_config: dict[str, Any] | None = None,
    ) -> None:
        """初始化 EventBus。

        Args:
            backend: 后端。
            redis_url: RedisURL。
            kafka_config: 配置。
        """
        self.backend = backend
        self.redis_url = redis_url
        self.kafka_config = kafka_config or {}
        self._subscribers: dict[EventType, list[SubscriberCallback]] = defaultdict(list)
        self._running = False

    def subscribe(
        self,
        event_type: EventType,
        callback: SubscriberCallback,
    ) -> None:
        """订阅指定类型的事件。

        Args:
            event_type: 事件类型。
            callback: 回调。
        """
        self._subscribers[event_type].append(callback)
        logger.info(
            "Subscriber registered for %s (total: %d)",
            event_type.value,
            len(self._subscribers[event_type]),
        )

    async def publish(self, event: AgentEvent) -> None:
        """发布事件到事件总线。

        Args:
            event: 待处理事件。
        """
        subscribers = self._subscribers.get(event.event_type, [])

        if not subscribers:
            logger.debug(
                "No subscribers for %s (correlation_id=%s)",
                event.event_type.value,
                event.correlation_id,
            )
            return

        logger.info(
            "Publishing %s to %d subscribers (correlation_id=%s, source=%s)",
            event.event_type.value,
            len(subscribers),
            event.correlation_id,
            event.source_agent,
        )

        # 并发分发给所有订阅者，异常隔离
        tasks = [self._safe_invoke(callback, event) for callback in subscribers]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _safe_invoke(
        self,
        callback: SubscriberCallback,
        event: AgentEvent,
    ) -> None:
        """安全调用订阅者回调，捕获异常防止单个订阅者故障影响其他订阅者。

        Args:
            callback: 回调。
            event: 待处理事件。
        """
        try:
            await callback(event)
        except Exception as e:
            logger.error(
                "Subscriber callback failed for %s (correlation_id=%s): %s",
                event.event_type.value,
                event.correlation_id,
                e,
                exc_info=True,
            )

    async def start(self) -> None:
        """启动事件总线（连接后端、开始消费循环）。"""
        self._running = True
        logger.info("EventBus started (backend=%s)", self.backend)

    async def stop(self) -> None:
        """停止事件总线，清理资源。"""
        self._running = False
        logger.info("EventBus stopped")
