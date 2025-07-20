from __future__ import annotations

import asyncio

from agentforge.platform.infrastructure.db.base import create_session_factory
from agentforge.platform.infrastructure.kafka_publisher import KafkaEventPublisher
from agentforge.platform.infrastructure.logging_event_publisher import LoggingEventPublisher
from agentforge.platform.infrastructure.outbox_dispatcher import OutboxDispatcher
from agentforge.platform.infrastructure.outbox_store import SQLAlchemyOutboxStore
from agentforge.platform.infrastructure.outbox_worker import OutboxWorker
from agentforge.platform.observability.tracing import configure_tracing
from agentforge.platform.settings import get_settings


async def run_outbox_worker() -> None:
    settings = get_settings()
    configure_tracing(endpoint=settings.otel_exporter_otlp_endpoint)
    session_factory = create_session_factory(settings.database_url)
    store = SQLAlchemyOutboxStore(session_factory)
    if settings.kafka_bootstrap_servers:
        publisher = KafkaEventPublisher(
            bootstrap_servers=settings.kafka_bootstrap_servers,
            topic=settings.kafka_topic,
        )
    else:
        publisher = LoggingEventPublisher()
    dispatcher = OutboxDispatcher(store, publisher)
    worker = OutboxWorker(dispatcher, interval_seconds=settings.outbox_poll_interval_seconds)
    await worker.run_forever()


if __name__ == "__main__":
    asyncio.run(run_outbox_worker())
