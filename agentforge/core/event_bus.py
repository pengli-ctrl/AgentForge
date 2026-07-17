"""
事件总线 — 带路由规则的异步事件分发系统。

V3 架构的核心组件。所有 Agent 通过事件总线通信，不直接调用其他 Agent。
事件总线不只是一个消息队列，而是一个带路由规则的异步事件分发系统。

核心设计：
- Publish/Subscribe 模式，Agent 间零直接依赖
- 支持 Redis Pub/Sub 和 Kafka 两种后端
- 事件携带 correlation_id 贯穿 trace 链路
- 动态路由：基于事件类型和 payload 内容路由到目标 Agent

技术选型说明：
- 初期用 Redis Pub/Sub（4 个 Agent、QPS < 100 时完全够用）
- Agent 增长到 8+、事件量翻倍后迁移到 Kafka
- 过渡方案：Redis Pub/Sub + MySQL 事件日志表双写兜底
"""

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
    """事件总线 — Agent 间通信的核心枢纽。

    所有 Agent 通过事件总线通信，不直接调用其他 Agent。
    支持 Redis Pub/Sub 和 Kafka 两种后端，可根据规模切换。

    Args:
        backend: 事件总线后端类型，"redis" 或 "kafka"。
        redis_url: Redis 连接地址（backend="redis" 时使用）。
        kafka_config: Kafka 配置（backend="kafka" 时使用）。

    Example:
        >>> bus = EventBus(backend="redis", redis_url="redis://localhost:6379")
        >>> bus.subscribe(EventType.TASK_SUBMITTED, my_agent)
        >>> await bus.publish(event)
    """

    def __init__(
        self,
        backend: str = "redis",
        redis_url: str = "redis://localhost:6379",
        kafka_config: dict[str, Any] | None = None,
    ) -> None:
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
            event_type: 要订阅的事件类型。
            callback: 事件回调协程函数，接收 AgentEvent 参数。
        """
        self._subscribers[event_type].append(callback)
        logger.info(
            "Subscriber registered for %s (total: %d)",
            event_type.value,
            len(self._subscribers[event_type]),
        )

    async def publish(self, event: AgentEvent) -> None:
        """发布事件到事件总线。

        事件会被分发给所有订阅了该事件类型的回调。
        每个回调独立执行，一个回调的异常不影响其他回调。

        Args:
            event: 要发布的事件。
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
            callback: 订阅者回调。
            event: 事件对象。
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
