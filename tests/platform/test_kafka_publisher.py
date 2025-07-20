import pytest

from agentforge.platform.domain.events import EventEnvelope
from agentforge.platform.infrastructure.kafka_publisher import KafkaEventPublisher


class FakeProducer:
    def __init__(self, **kwargs) -> None:
        self.started = False
        self.stopped = False
        self.messages: list[tuple[str, bytes, bytes]] = []

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True

    async def send_and_wait(self, topic: str, payload: bytes, key: bytes) -> None:
        self.messages.append((topic, payload, key))


@pytest.mark.asyncio
async def test_kafka_publisher_serializes_event() -> None:
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
