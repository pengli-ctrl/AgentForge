"""Outbox操作测试模块。

本测试模块验证 test_outbox_operations 覆盖的业务路径、边界条件和回归场景。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
-
主要函数：make_sqlalchemy、test_sqlalchemy_outbox_list_detail_discard_count、test_memory_outbox_store_m
    atches_surface、test_outbox_admin_endpoints_sqlalchemy、test_outbox_memory_endpoints。
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from agentforge.platform.api.app import create_platform_app
from agentforge.platform.domain.events import EventEnvelope
from agentforge.platform.infrastructure.db.base import Base
from agentforge.platform.infrastructure.db.models import OutboxEventRecord
from agentforge.platform.infrastructure.memory_outbox_store import MemoryOutboxStore
from agentforge.platform.infrastructure.outbox_store import SQLAlchemyOutboxStore
from agentforge.platform.runtime import build_memory_container, build_sqlalchemy_container


async def make_sqlalchemy():
    """构造SQLAlchemy。

    Returns:
        处理结果。
    """
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    return engine, session_factory


def _event(
    event_id: str, tenant: str = "tenant-1", event_type: str = "ticket.created"
) -> EventEnvelope:
    """处理事件。

    Args:
        event_id: 事件 ID。
        tenant: 租户。
        event_type: 事件类型。

    Returns:
        事件结果。
    """
    return EventEnvelope(
        event_id=event_id,
        event_type=event_type,
        tenant_id=tenant,
        task_id=f"task-{event_id}",
        trace_id=f"trace-{event_id}",
        producer="test",
        payload={"key": event_id},
    )


@pytest.mark.asyncio
async def test_sqlalchemy_outbox_list_detail_discard_count() -> None:
    """验证SQLAlchemyOutbox查询详情丢弃数量对应的测试场景。"""
    engine, session_factory = await make_sqlalchemy()
    store = SQLAlchemyOutboxStore(session_factory)

    async with session_factory() as session:
        async with session.begin():
            session.add(OutboxEventRecord.from_event(_event("e1", tenant="t1")))
            session.add(OutboxEventRecord.from_event(_event("e2", tenant="t1")))
            session.add(OutboxEventRecord.from_event(_event("e3", tenant="t2")))

    events, _cursor = await store.list_events(limit=100)
    assert len(events) == 3
    assert set(e["status"] for e in events) == {"pending"}

    t1_only, _ = await store.list_events(tenant_id="t1", limit=100)
    assert {e["event_id"] for e in t1_only} == {"e1", "e2"}

    paged, cursor = await store.list_events(limit=2)
    assert len(paged) == 2
    assert cursor is not None

    detail = await store.get_event("t1", "e1")
    assert detail is not None and detail["event_id"] == "e1"

    counts = await store.count_events()
    assert counts["pending"] == 3

    assert await store.discard("t1", "e1") is True
    discarded = await store.get_event("t1", "e1")
    assert discarded["status"] == "discarded"
    counts_after = await store.count_events()
    assert counts_after["pending"] == 2
    assert counts_after["discarded"] == 1

    assert await store.replay("e1") is True
    assert (await store.get_event("t1", "e1"))["status"] == "pending"
    await engine.dispose()


@pytest.mark.asyncio
async def test_memory_outbox_store_matches_surface() -> None:
    """验证记忆Outbox存储匹配结果对应的测试场景。"""
    store = MemoryOutboxStore()
    await store.enqueue(_event("m1", tenant="t1"))
    await store.enqueue(_event("m2", tenant="t1"))
    await store.enqueue(_event("m3", tenant="t2"))

    assert len(await store.fetch_pending()) == 3
    t1, _ = await store.list_events(tenant_id="t1")
    assert {e["event_id"] for e in t1} == {"m1", "m2"}
    assert (await store.count_events())["pending"] == 3
    assert await store.discard("t1", "m1") is True
    assert (await store.get_event("t1", "m1"))["status"] == "discarded"
    assert await store.replay("m1") is True
    assert (await store.get_event("t1", "m1"))["status"] == "pending"


def test_outbox_admin_endpoints_sqlalchemy() -> None:
    """验证Outbox管理端点SQLAlchemy对应的测试场景。"""
    import asyncio

    async def setup():
        """装配测试环境。

        Returns:
            处理结果。
        """
        engine, session_factory = await make_sqlalchemy()
        container = build_sqlalchemy_container(session_factory)
        async with session_factory() as session:
            async with session.begin():
                session.add(OutboxEventRecord.from_event(_event("adm1", tenant="t1")))
        return engine, container

    engine, container = asyncio.run(setup())
    client = TestClient(create_platform_app(container))

    listed = client.get("/v1/outbox/events").json()
    assert listed["events"][0]["event_id"] == "adm1"
    assert "next_cursor" in listed

    count = client.get("/v1/outbox/events/count").json()
    assert count["pending"] == 1

    detail = client.get("/v1/outbox/events/adm1").json()
    assert detail["event"]["event_id"] == "adm1"

    discarded = client.post("/v1/outbox/adm1/discard").json()
    assert discarded["discarded"] is True

    asyncio.run(engine.dispose())


def test_outbox_memory_endpoints() -> None:
    """验证Outbox记忆端点对应的测试场景。"""
    import asyncio

    container = build_memory_container()
    client = TestClient(create_platform_app(container))
    store = container.outbox_store
    assert isinstance(store, MemoryOutboxStore)
    asyncio.run(store.enqueue(_event("mem1", tenant="t1")))

    listed = client.get("/v1/outbox/events").json()
    assert listed["events"][0]["event_id"] == "mem1"
    assert client.post("/v1/outbox/mem1/discard").json()["discarded"] is True
