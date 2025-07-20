from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from agentforge.platform.api.app import create_platform_app
from agentforge.platform.infrastructure.db.base import Base
from agentforge.platform.infrastructure.outbox_dispatcher import OutboxDispatcher
from agentforge.platform.infrastructure.outbox_store import SQLAlchemyOutboxStore
from agentforge.platform.runtime import build_sqlalchemy_container


class FailingPublisher:
    async def publish(self, event):
        raise RuntimeError("kafka unavailable")


def test_outbox_admin_list_and_replay() -> None:
    import asyncio

    async def setup():
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
                "message_id": "admin-msg-1",
                "text": "How do I use this product?",
            }
        )
        store = SQLAlchemyOutboxStore(session_factory, max_attempts=1)
        dispatcher = OutboxDispatcher(store, FailingPublisher())
        await dispatcher.dispatch_once()
        return engine, container

    engine, container = asyncio.run(setup())
    client = TestClient(create_platform_app(container))
    failed = client.get("/v1/outbox/failed").json()["events"]
    assert len(failed) == 1
    response = client.post(f"/v1/outbox/{failed[0]['event_id']}/replay")
    assert response.status_code == 200
    assert response.json()["replayed"] is True
    asyncio.run(engine.dispose())
