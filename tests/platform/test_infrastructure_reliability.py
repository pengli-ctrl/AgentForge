"""测试基础设施测试模块。"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from agentforge.platform.domain.events import EventEnvelope
from agentforge.platform.infrastructure.db.base import Base
from agentforge.platform.infrastructure.outbox_dispatcher import OutboxDispatcher
from agentforge.platform.infrastructure.outbox_store import SQLAlchemyOutboxStore
from agentforge.platform.infrastructure.valkey_coordination import ValkeyCoordination


class FlakyPublisher:
    """按指定失败次数工作的不稳定事件发布器。"""

    def __init__(self, failures: int) -> None:
        """初始化不稳定发布器。

        Args:
            failures: 输入参数。
        """
        self.failures = failures
        self.published: list[str] = []

    async def publish(self, event: EventEnvelope) -> None:
        """发布不稳定发布器。

        Args:
            event: 待处理事件。

        Raises:
            RuntimeError: 运行时依赖或状态不满足要求时抛出。
        """
        if self.failures > 0:
            self.failures -= 1
            raise RuntimeError("publisher unavailable")
        self.published.append(event.event_id)


def _event(event_id: str) -> EventEnvelope:
    """处理事件。

    Args:
        event_id: 事件 ID。

    Returns:
        事件结果。
    """
    return EventEnvelope(
        event_id=event_id,
        event_type="support.ticket.created.v1",
        tenant_id="tenant-reliability",
        task_id="task-1",
        trace_id="trace-1",
        producer="test",
    )


async def _store() -> tuple[object, SQLAlchemyOutboxStore]:
    """保存当前记录。

    Returns:
        结果元组。
    """
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    return engine, SQLAlchemyOutboxStore(session_factory, max_attempts=2)


@pytest.mark.asyncio
async def test_outbox_handler_is_idempotent_when_publisher_retries() -> None:
    """验证Outbox处理器是否幂等当发布器重试对应的测试场景。"""
    engine, store = await _store()
    await store.enqueue(_event("evt-handler-once"))
    handler_calls = 0

    async def handler(event: EventEnvelope) -> None:
        """处理测试场景中的异步请求。

        Args:
            event: 待处理事件。
        """
        nonlocal handler_calls
        handler_calls += 1

    publisher = FlakyPublisher(failures=1)
    dispatcher = OutboxDispatcher(
        store,
        publisher,
        event_handlers={"support.ticket.created.v1": handler},
    )

    assert await dispatcher.dispatch_once() == 0
    assert await dispatcher.dispatch_once() == 1
    assert handler_calls == 1
    assert publisher.published == ["evt-handler-once"]
    detail = await store.get_event("tenant-reliability", "evt-handler-once")
    assert detail is not None and detail["status"] == "published"
    await engine.dispose()


@pytest.mark.asyncio
async def test_handler_failure_is_released_and_retried() -> None:
    """验证处理器失败是否已释放及已重试对应的测试场景。"""
    engine, store = await _store()
    await store.enqueue(_event("evt-handler-retry"))
    attempts = 0

    async def handler(event: EventEnvelope) -> None:
        """处理测试场景中的异步请求。

        Args:
            event: 待处理事件。

        Raises:
            RuntimeError: 运行时依赖或状态不满足要求时抛出。
        """
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("temporary handler failure")

    dispatcher = OutboxDispatcher(
        store,
        FlakyPublisher(failures=0),
        event_handlers={"support.ticket.created.v1": handler},
    )

    assert await dispatcher.dispatch_once() == 0
    assert await dispatcher.dispatch_once() == 1
    assert attempts == 2
    detail = await store.get_event("tenant-reliability", "evt-handler-retry")
    assert detail is not None and detail["status"] == "published"
    await engine.dispose()


@pytest.mark.asyncio
async def test_valkey_rate_limit_cache_and_lock() -> None:
    """验证Valkey速率限制缓存及锁对应的测试场景。"""
    fakeredis = pytest.importorskip("fakeredis")
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    coordination = ValkeyCoordination(client, prefix="test")

    first = await coordination.rate_limit(
        "tenant-a:api",
        capacity=2,
        refill_rate=1,
        now=100.0,
    )
    second = await coordination.rate_limit(
        "tenant-a:api",
        capacity=2,
        refill_rate=1,
        now=100.1,
    )
    blocked = await coordination.rate_limit(
        "tenant-a:api",
        capacity=2,
        refill_rate=1,
        now=100.2,
    )
    refilled = await coordination.rate_limit(
        "tenant-a:api",
        capacity=2,
        refill_rate=1,
        now=101.5,
    )
    assert first.allowed is True
    assert second.allowed is True
    assert blocked.allowed is False
    assert blocked.retry_after_ms > 0
    assert refilled.allowed is True

    await coordination.set_json("tenant-a:doc:1", {"title": "A"}, ttl_seconds=60)
    await coordination.set_json("tenant-a:doc:2", {"title": "B"}, ttl_seconds=60)
    assert await coordination.get_json("tenant-a:doc:1") == {"title": "A"}
    assert await coordination.invalidate_prefix("tenant-a:") == 2
    assert await coordination.get_json("tenant-a:doc:1") is None

    assert await coordination.acquire_lock("nightly", "owner-a", ttl_seconds=30) is True
    assert await coordination.acquire_lock("nightly", "owner-b", ttl_seconds=30) is False
    assert await coordination.release_lock("nightly", "owner-b") is False
    assert await coordination.release_lock("nightly", "owner-a") is True
    assert await coordination.acquire_lock("nightly", "owner-b", ttl_seconds=30) is True
    await coordination.close()
