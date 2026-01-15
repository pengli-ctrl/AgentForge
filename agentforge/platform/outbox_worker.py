"""AgentForge 平台代码：outbox_worker。

本模块负责 outbox_worker 相关的平台能力，是 平台代码 的组成部分。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要函数：run_outbox_worker。
"""

from __future__ import annotations

import asyncio

from agentforge.platform.application.ports import EventPublisher
from agentforge.platform.infrastructure.db.base import create_session_factory
from agentforge.platform.infrastructure.kafka_publisher import KafkaEventPublisher
from agentforge.platform.infrastructure.logging_event_publisher import LoggingEventPublisher
from agentforge.platform.infrastructure.outbox_dispatcher import OutboxDispatcher
from agentforge.platform.infrastructure.outbox_store import SQLAlchemyOutboxStore
from agentforge.platform.infrastructure.outbox_worker import OutboxWorker
from agentforge.platform.observability.tracing import configure_tracing
from agentforge.platform.settings import get_settings


async def run_outbox_worker() -> None:
    """执行完整流程，并返回调用方需要的结果。

    Returns:
        None，函数执行后的结果。
    """
    settings = get_settings()
    configure_tracing(endpoint=settings.otel_exporter_otlp_endpoint)
    session_factory = create_session_factory(settings.database_url)
    store = SQLAlchemyOutboxStore(session_factory)
    publisher: EventPublisher
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
