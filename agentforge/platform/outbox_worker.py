"""Outbox工作进程模块。"""

from __future__ import annotations

import asyncio

from agentforge.platform.application.ports import EventPublisher
from agentforge.platform.infrastructure.kafka_publisher import KafkaEventPublisher
from agentforge.platform.infrastructure.logging_event_publisher import LoggingEventPublisher
from agentforge.platform.infrastructure.outbox_dispatcher import OutboxDispatcher
from agentforge.platform.infrastructure.outbox_worker import OutboxWorker
from agentforge.platform.observability.tracing import configure_tracing
from agentforge.platform.settings import get_settings


async def run_outbox_worker() -> None:
    """运行Outbox工作进程。"""
    settings = get_settings()
    configure_tracing(endpoint=settings.otel_exporter_otlp_endpoint)
    from agentforge.platform.api.app import create_platform_app

    app = create_platform_app()
    container = app.state.container
    handlers = app.state.module_registry.event_handlers()
    publisher: EventPublisher
    if settings.kafka_bootstrap_servers:
        publisher = KafkaEventPublisher(
            bootstrap_servers=settings.kafka_bootstrap_servers,
            topic=settings.kafka_topic,
        )
    else:
        publisher = LoggingEventPublisher()
    dispatcher = OutboxDispatcher(
        container.outbox_store,
        publisher,
        event_handlers=handlers,
    )
    worker = OutboxWorker(dispatcher, interval_seconds=settings.outbox_poll_interval_seconds)
    await worker.run_forever()


if __name__ == "__main__":
    asyncio.run(run_outbox_worker())
