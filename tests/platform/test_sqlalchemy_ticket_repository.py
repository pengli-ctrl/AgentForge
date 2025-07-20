import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from agentforge.platform.domain.ticket import TicketStatus
from agentforge.platform.infrastructure.db.base import Base
from agentforge.platform.infrastructure.memory_event_publisher import MemoryEventPublisher
from agentforge.platform.infrastructure.outbox_dispatcher import OutboxDispatcher
from agentforge.platform.runtime import build_sqlalchemy_container


async def make_container():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    return engine, build_sqlalchemy_container(session_factory)


@pytest.mark.asyncio
async def test_sqlalchemy_repository_persists_and_deduplicates() -> None:
    engine, container = await make_container()
    event = {
        "tenant_id": "tenant-1",
        "source": "feishu",
        "message_id": "msg-sql-1",
        "text": "How do I use this product?",
    }
    first = await container.ticket_service.create_from_event(event)
    second = await container.ticket_service.create_from_event(event)
    assert first.ticket_id == second.ticket_id
    assert first.status == TicketStatus.WAITING_REVIEW
    await engine.dispose()


@pytest.mark.asyncio
async def test_outbox_contains_event_and_dispatcher_marks_published() -> None:
    engine, container = await make_container()
    await container.ticket_service.create_from_event(
        {
            "tenant_id": "tenant-1",
            "source": "feishu",
            "message_id": "msg-sql-2",
            "text": "How do I use this product?",
        }
    )
    assert len(await container.outbox_store.fetch_pending()) == 1
    publisher = MemoryEventPublisher()
    dispatcher = OutboxDispatcher(container.outbox_store, publisher)
    assert await dispatcher.dispatch_once() == 1
    assert len(publisher.events) == 1
    assert await container.outbox_store.fetch_pending() == []
    await engine.dispose()


@pytest.mark.asyncio
async def test_high_risk_ticket_requires_and_records_approval() -> None:
    engine, container = await make_container()
    ticket = await container.ticket_service.create_from_event(
        {
            "tenant_id": "tenant-1",
            "source": "feishu",
            "message_id": "msg-sql-3",
            "text": "I want a refund and I have a complaint",
        }
    )
    assert ticket.status == TicketStatus.WAITING_APPROVAL
    updated = await container.ticket_service.apply_approval(
        tenant_id="tenant-1",
        ticket_id=ticket.ticket_id,
        decision="approve",
        decided_by="supervisor-1",
    )
    assert updated.status == TicketStatus.READY_TO_PUBLISH
    assert updated.metadata["approval"]["decided_by"] == "supervisor-1"
    await engine.dispose()
