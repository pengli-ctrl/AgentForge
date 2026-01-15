"""AgentForge 平台测试层：test_kafka_publisher。

本测试模块验证 test_kafka_publisher 覆盖的业务路径、边界条件和回归场景。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：FakeProducer。
- 主要函数：test_kafka_publisher_serializes_event。
"""

import pytest

from agentforge.platform.domain.events import EventEnvelope
from agentforge.platform.infrastructure.kafka_publisher import KafkaEventPublisher


class FakeProducer:
    """FakeProducer。

    FakeProducer 封装相关领域行为，保持职责单一并降低调用方复杂度。

    主要成员：
    - 方法 start()。
    - 方法 stop()。
    - 方法 send_and_wait()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    def __init__(self, **kwargs) -> None:
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Args:
            **kwargs: Any，调用方传入的 **kwargs 参数。

        Returns:
            None，函数执行后的结果。
        """
        self.started = False
        self.stopped = False
        self.messages: list[tuple[str, bytes, bytes]] = []

    async def start(self) -> None:
        """执行 start 对应的核心操作，并保持调用契约稳定。

        Returns:
            None，函数执行后的结果。
        """
        self.started = True

    async def stop(self) -> None:
        """执行 stop 对应的核心操作，并保持调用契约稳定。

        Returns:
            None，函数执行后的结果。
        """
        self.stopped = True

    async def send_and_wait(self, topic: str, payload: bytes, key: bytes) -> None:
        """执行 send_and_wait 对应的逻辑，并返回处理结果。

        Args:
            topic: str，调用方传入的 topic 参数。
            payload: bytes，调用方传入的 payload 参数。
            key: bytes，调用方传入的 key 参数。

        Returns:
            None，函数执行后的结果。
        """
        self.messages.append((topic, payload, key))


@pytest.mark.asyncio
async def test_kafka_publisher_serializes_event() -> None:
    """验证 kafka_publisher_serializes_event 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    producer = FakeProducer()
    publisher = KafkaEventPublisher(
        bootstrap_servers="kafka:9092",
        topic="events",
        producer_factory=lambda **kwargs: producer,
    )
    event = EventEnvelope(
        event_id="event-1",
        event_type="ticket.created",
        tenant_id="tenant-1",
        task_id="ticket-1",
        trace_id="trace-1",
        producer="test",
    )
    await publisher.publish(event)
    await publisher.stop()
    assert producer.messages[0][0] == "events"
    assert b"ticket.created" in producer.messages[0][1]
    assert producer.messages[0][2] == b"tenant-1"
    assert producer.stopped is True
