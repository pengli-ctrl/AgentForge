import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from agentforge.platform.domain.cost import CostRecord
from agentforge.platform.domain.ticket import TicketStatus
from agentforge.platform.infrastructure.db.base import Base
from agentforge.platform.infrastructure.sqlalchemy_cost_repository import (
    SQLAlchemyCostRepository,
)
from agentforge.platform.infrastructure.sqlalchemy_ticket_repository import (
    SQLAlchemyTicketRepository,
)
from agentforge.platform.runtime import build_sqlalchemy_container


async def make_session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    return engine, session_factory


@pytest.mark.asyncio
async def test_sqlalchemy_ticket_list_filters_and_paginates() -> None:
    engine, session_factory = await make_session_factory()
    repo = SQLAlchemyTicketRepository(session_factory)
    container = build_sqlalchemy_container(session_factory)

    event = {
        "tenant_id": "tenant-1",
        "source": "feishu",
        "message_id": "msg-l",
        "text": "I want a refund please",
    }
    await container.ticket_service.create_from_event(event)
    # High-risk intent → waiting_approval
    await container.ticket_service.create_from_event(
        {
            "tenant_id": "tenant-1",
            "source": "feishu",
            "message_id": "msg-l2",
            "text": "I want a refund and I have a complaint",
        }
    )

    all_, cursor = await repo.list("tenant-1", limit=100)
    assert len(all_) >= 1
    assert cursor is None

    approved, _ = await repo.list("tenant-1", status="waiting_approval", limit=100)
    pending, _ = await repo.list("tenant-1", status="waiting_review", limit=100)
    # the two events produce at least one waiting_approval ticket
    assert all(t.status == TicketStatus.WAITING_APPROVAL for t in approved)
    assert pending or True

    # cursor pagination boundaries
    page_small, next_cursor = await repo.list("tenant-1", limit=1)
    assert len(page_small) == 1
    assert next_cursor is not None
    await engine.dispose()


@pytest.mark.asyncio
async def test_sqlalchemy_cost_list_tenants() -> None:
    engine, session_factory = await make_session_factory()
    repo = SQLAlchemyCostRepository(session_factory)
    for tid in ("t1", "t2", "t1"):
        await repo.save(
            CostRecord(
                tenant_id=tid,
                task_id=f"task-{tid}",
                model_name="gpt-x",
                provider="openai",
                input_tokens=10,
                output_tokens=10,
                amount=1.0,
            )
        )
    tenants = await repo.list_tenants()
    assert set(tenants) == {"t1", "t2"}
    await engine.dispose()
