"""AgentForge 平台基础设施层：kafka_publisher。

本模块负责 kafka_publisher 相关的平台能力，是 平台基础设施层 的组成部分。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：KafkaEventPublisher。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from agentforge.platform.domain.events import EventEnvelope


class KafkaEventPublisher:
    """KafkaEventPublisher。

    KafkaEventPublisher 封装相关领域行为，保持职责单一并降低调用方复杂度。

    主要成员：
    - 方法 start()。
    - 方法 stop()。
    - 方法 publish()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    def __init__(
        self,
        bootstrap_servers: str,
        topic: str,
        producer_factory: Callable[..., Any] | None = None,
    ) -> None:
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Args:
            bootstrap_servers: str，调用方传入的 bootstrap_servers 参数。
            topic: str，调用方传入的 topic 参数。
            producer_factory: Callable[..., Any] | None，调用方传入的 producer_factory 参数。

        Returns:
            None，函数执行后的结果。
        """
        self._bootstrap_servers = bootstrap_servers
        self._topic = topic
        self._producer_factory = producer_factory
        self._producer: Any | None = None

    async def start(self) -> None:
        """执行 start 对应的核心操作，并保持调用契约稳定。

        Returns:
            None，函数执行后的结果。
        """
        if self._producer is not None:
            return
        if self._producer_factory is None:
            from aiokafka import AIOKafkaProducer

            self._producer = AIOKafkaProducer(bootstrap_servers=self._bootstrap_servers)
        else:
            self._producer = self._producer_factory(bootstrap_servers=self._bootstrap_servers)
        await self._producer.start()

    async def stop(self) -> None:
        """执行 stop 对应的核心操作，并保持调用契约稳定。

        Returns:
            None，函数执行后的结果。
        """
        if self._producer is not None:
            await self._producer.stop()
            self._producer = None

    async def publish(self, event: EventEnvelope) -> None:
        """执行 publish 对应的核心操作，并保持调用契约稳定。

        Args:
            event: EventEnvelope，调用方传入的 event 参数。

        Returns:
            None，函数执行后的结果。
        """
        if self._producer is None:
            await self.start()
        payload = event.model_dump_json().encode("utf-8")
        await self._producer.send_and_wait(
            self._topic,
            payload,
            key=event.tenant_id.encode("utf-8"),
        )
