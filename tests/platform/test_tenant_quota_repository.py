from __future__ import annotations

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from agentforge.platform.domain.tenant_quota import TenantQuota
from agentforge.platform.infrastructure.db.base import Base
from agentforge.platform.infrastructure.memory_tenant_quota_repository import (
    MemoryTenantQuotaRepository,
)
from agentforge.platform.infrastructure.sqlalchemy_tenant_quota_repository import (
    SQLAlchemyTenantQuotaRepository,
)


def _quota(tenant_id: str, limit: float) -> TenantQuota:
    return TenantQuota(
        tenant_id=tenant_id,
        monthly_limit=limit,
        warning_threshold=0.8,
        hard_limit=1.0,
        enabled=True,
    )


def _sqlite_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    return engine, async_sessionmaker(engine, expire_on_commit=False)


async def test_memory_quota_upsert_get_delete() -> None:
    repo = MemoryTenantQuotaRepository()
    await repo.upsert(_quota("t1", 100.0))
    assert (await repo.get("t1")).monthly_limit == 100.0
    assert await repo.get("missing") is None
    await repo.upsert(_quota("t2", 50.0))
    assert [q.tenant_id for q in await repo.list()] == ["t1", "t2"]
    await repo.delete("t1")
    assert await repo.get("t1") is None


async def test_sqlalchemy_quota_roundtrip() -> None:
    engine, session_factory = _sqlite_factory()
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    repo = SQLAlchemyTenantQuotaRepository(session_factory)
    await repo.upsert(_quota("t1", 200.0))
    fetched = await repo.get("t1")
    assert fetched is not None
    assert fetched.monthly_limit == 200.0
    assert fetched.hard_limit == 1.0
    listed = await repo.list()
    assert [q.tenant_id for q in listed] == ["t1"]
    await repo.delete("t1")
    assert await repo.get("t1") is None
    await engine.dispose()


async def test_quota_usage_status() -> None:
    quota = _quota("t1", 100.0)
    assert quota.usage_status(50.0)["status"] == "active"
    assert quota.usage_status(85.0)["status"] == "warning"
    assert quota.usage_status(100.0)["status"] == "blocked"
    disabled = _quota("t2", 100.0)
    disabled.enabled = False
    assert disabled.usage_status(5000.0)["status"] == "active"
