"""AgentForge 平台测试层：test_connector_repository。

本测试模块验证 test_connector_repository 覆盖的业务路径、边界条件和回归场景。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要函数：test_memory_repository_roundtrip、test_sqlalchemy_repository_roundtrip_and_tenancy。
"""

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
    """执行 _spec 对应的逻辑，并返回处理结果。

    Args:
        connector_id: str，调用方传入的 connector_id 参数。
        tenant_id: str，调用方传入的 tenant_id 参数。

    Returns:
        ConnectorSpec，函数执行后的结果。
    """
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
    """验证 memory_repository_roundtrip 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    repo = MemoryConnectorRepository()
    spec = _spec("conn-m1", "t1")
    await repo.save_spec(spec)
    assert await repo.get_spec("conn-m1") == spec
    assert len(await repo.list_specs("t1")) == 1
    assert await repo.list_specs("t2") == []
    await repo.delete_spec("conn-m1")
    assert await repo.get_spec("conn-m1") is None


async def _make_sqlalchemy_repo():
    """执行 _make_sqlalchemy_repo 对应的逻辑，并返回处理结果。

    Returns:
        None，函数执行后的结果。
    """
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
    """验证 sqlalchemy_repository_roundtrip_and_tenancy 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
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
