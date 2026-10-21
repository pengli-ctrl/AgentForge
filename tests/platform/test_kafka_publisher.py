"""发布器测试模块。

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
    """用于测试的模拟 Kafka 生产者。"""

    def __init__(self, **kwargs) -> None:
        """初始化模拟。

        Args:
            kwargs: 关键字参数。
        """
        self.started = False
        self.stopped = False
        self.messages: list[tuple[str, bytes, bytes]] = []

    async def start(self) -> None:
        """启动模拟。"""
        self.started = True

    async def stop(self) -> None:
        """停止模拟。"""
        self.stopped = True

    async def send_and_wait(self, topic: str, payload: bytes, key: bytes) -> None:
        """发送及。

        Args:
            topic: 输入参数。
            payload: 事件、工作流或请求载荷。
            key: 缓存或配置键。
        """
        self.messages.append((topic, payload, key))


@pytest.mark.asyncio
async def test_kafka_publisher_serializes_event() -> None:
    """验证发布器序列化事件对应的测试场景。"""
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
