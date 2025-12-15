from __future__ import annotations

from collections.abc import Callable
from typing import Any

from agentforge.platform.domain.events import EventEnvelope


class KafkaEventPublisher:
    def __init__(
        self,
        bootstrap_servers: str,
        topic: str,
        producer_factory: Callable[..., Any] | None = None,
    ) -> None:
        self._bootstrap_servers = bootstrap_servers
        self._topic = topic
        self._producer_factory = producer_factory
        self._producer: Any | None = None

    async def start(self) -> None:
        if self._producer is not None:
            return
        if self._producer_factory is None:
            from aiokafka import AIOKafkaProducer

            self._producer = AIOKafkaProducer(bootstrap_servers=self._bootstrap_servers)
        else:
            self._producer = self._producer_factory(bootstrap_servers=self._bootstrap_servers)
        await self._producer.start()

    async def stop(self) -> None:
        if self._producer is not None:
            await self._producer.stop()
            self._producer = None

    async def publish(self, event: EventEnvelope) -> None:
        if self._producer is None:
            await self.start()
        payload = event.model_dump_json().encode("utf-8")
        await self._producer.send_and_wait(
            self._topic,
            payload,
            key=event.tenant_id.encode("utf-8"),
        )
