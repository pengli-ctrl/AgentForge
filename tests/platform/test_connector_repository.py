import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from agentforge.platform.domain.connector import (
    ConnectorKind,
    ConnectorRiskLevel,
    ConnectorSpec,
)
from agentforge.platform.infrastructure.db.base import Base
from agentforge.platform.infrastructure.memory_connector_repository import (
    MemoryConnectorRepository,
)
from agentforge.platform.infrastructure.sqlalchemy_connector_repository import (
    SQLAlchemyConnectorRepository,
)


def _spec(connector_id: str, tenant_id: str) -> ConnectorSpec:
    return ConnectorSpec(
        connector_id=connector_id,
        tenant_id=tenant_id,
        name="openapi",
        kind=ConnectorKind.OPENAPI,
        version="1.0",
        risk_level=ConnectorRiskLevel.MEDIUM,
        endpoint="https://crm.test",
        allowed_actions=["writeback", "ping"],
        config={"auth_header": "Authorization"},
    )


@pytest.mark.asyncio
async def test_memory_repository_roundtrip() -> None:
    repo = MemoryConnectorRepository()
    spec = _spec("conn-m1", "t1")
    await repo.save_spec(spec)
    assert await repo.get_spec("conn-m1") == spec
    assert len(await repo.list_specs("t1")) == 1
    assert await repo.list_specs("t2") == []
    await repo.delete_spec("conn-m1")
    assert await repo.get_spec("conn-m1") is None


async def _make_sqlalchemy_repo():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    return engine, SQLAlchemyConnectorRepository(session_factory)


@pytest.mark.asyncio
async def test_sqlalchemy_repository_roundtrip_and_tenancy() -> None:
    engine, repo = await _make_sqlalchemy_repo()
    spec1 = _spec("conn-s1", "t1")
    spec2 = _spec("conn-s2", "t2")
    await repo.save_spec(spec1)
    await repo.save_spec(spec2)
    assert await repo.get_spec("conn-s1") == spec1
    assert await repo.get_spec("conn-s2") == spec2
    assert {s.connector_id for s in await repo.list_specs("t1")} == {"conn-s1"}
    assert len(await repo.list_specs()) == 2
    await repo.delete_spec("conn-s1")
    assert await repo.get_spec("conn-s1") is None
    await engine.dispose()
