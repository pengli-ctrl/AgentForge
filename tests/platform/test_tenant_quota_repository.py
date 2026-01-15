"""AgentForge 平台测试层：test_tenant_quota_repository。

本测试模块验证 test_tenant_quota_repository 覆盖的业务路径、边界条件和回归场景。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要函数：test_memory_quota_upsert_get_delete、test_sqlalchemy_quota_roundtrip、test_quota_usage_status。
"""

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
    """执行 _quota 对应的逻辑，并返回处理结果。

    Args:
        tenant_id: str，调用方传入的 tenant_id 参数。
        limit: float，调用方传入的 limit 参数。

    Returns:
        TenantQuota，函数执行后的结果。
    """
    return TenantQuota(
        tenant_id=tenant_id,
        monthly_limit=limit,
        warning_threshold=0.8,
        hard_limit=1.0,
        enabled=True,
    )


def _sqlite_factory():
    """执行 _sqlite_factory 对应的逻辑，并返回处理结果。

    Returns:
        None，函数执行后的结果。
    """
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    return engine, async_sessionmaker(engine, expire_on_commit=False)


async def test_memory_quota_upsert_get_delete() -> None:
    """验证 memory_quota_upsert_get_delete 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    repo = MemoryTenantQuotaRepository()
    await repo.upsert(_quota("t1", 100.0))
    assert (await repo.get("t1")).monthly_limit == 100.0
    assert await repo.get("missing") is None
    await repo.upsert(_quota("t2", 50.0))
    assert [q.tenant_id for q in await repo.list()] == ["t1", "t2"]
    await repo.delete("t1")
    assert await repo.get("t1") is None


async def test_sqlalchemy_quota_roundtrip() -> None:
    """验证 sqlalchemy_quota_roundtrip 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
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
    """验证 quota_usage_status 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    quota = _quota("t1", 100.0)
    assert quota.usage_status(50.0)["status"] == "active"
    assert quota.usage_status(85.0)["status"] == "warning"
    assert quota.usage_status(100.0)["status"] == "blocked"
    disabled = _quota("t2", 100.0)
    disabled.enabled = False
    assert disabled.usage_status(5000.0)["status"] == "active"
