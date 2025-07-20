import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from agentforge.platform.infrastructure.db.base import Base
from agentforge.platform.infrastructure.outbox_dispatcher import OutboxDispatcher
from agentforge.platform.infrastructure.outbox_store import SQLAlchemyOutboxStore
from agentforge.platform.runtime import build_sqlalchemy_container


class FailingPublisher:
    async def publish(self, event):
        raise RuntimeError("broker unavailable")


@pytest.mark.asyncio
async def test_outbox_moves_to_failed_and_can_be_replayed() -> None:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    container = build_sqlalchemy_container(session_factory)
    await container.ticket_service.create_from_event(
        {
            "tenant_id": "tenant-1",
            "source": "feishu",
            "message_id": "retry-msg-1",
            "text": "How do I use this product?",
        }
    )
    store = SQLAlchemyOutboxStore(session_factory, max_attempts=2)
    dispatcher = OutboxDispatcher(store, FailingPublisher())
    await dispatcher.dispatch_once()
    await dispatcher.dispatch_once()
    failed = await store.list_failed()
    assert len(failed) == 1
    assert failed[0]["attempts"] == 2
    assert await store.replay(failed[0]["event_id"]) is True
    assert len(await store.fetch_pending()) == 1
    await engine.dispose()
