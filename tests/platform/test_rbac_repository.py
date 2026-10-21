"""RBAC仓储测试模块。

本测试模块验证 test_rbac_repository 覆盖的业务路径、边界条件和回归场景。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
-
主要函数：create_async_session_factory、test_memory_rbac_roundtrip_and_tenancy、test_sqlalchemy_rbac_ro
    undtrip_and_tenancy、test_sqlalchemy_role_and_assignment。
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from agentforge.platform.domain.rbac import Role, RoleAssignment
from agentforge.platform.infrastructure.db.base import Base
from agentforge.platform.infrastructure.memory_rbac_repository import MemoryRbacRepository
from agentforge.platform.infrastructure.sqlalchemy_rbac_repository import SQLAlchemyRbacRepository


def create_async_session_factory():
    """创建异步会话工厂。

    Returns:
        处理结果。
    """
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    return engine, async_sessionmaker(engine, expire_on_commit=False)


def _role(role_id: str, tenant_id: str, name: str) -> Role:
    """处理角色。

    Args:
        role_id: 角色 ID。
        tenant_id: 租户 ID，用于数据隔离。
        name: 资源或对象名称。

    Returns:
        角色结果。
    """
    return Role(
        role_id=role_id,
        tenant_id=tenant_id,
        name=name,
        description="test role",
        permissions=["ticket.read"],
        built_in=False,
    )


async def test_memory_rbac_roundtrip_and_tenancy() -> None:
    """验证记忆RBAC往返及租户隔离对应的测试场景。"""
    repo = MemoryRbacRepository()
    await repo.save_role(_role("r1", "t1", "support_admin"))
    await repo.save_role(_role("r2", "t2", "support_agent"))

    assert (await repo.get_role("t1", "r1")) is not None
    assert await repo.get_role("t1", "r2") is None  # 验证租户隔离，确保不同租户数据不会互相泄漏。
    assert [r.role_id for r in await repo.list_roles("t1")] == ["r1"]


async def test_sqlalchemy_rbac_roundtrip_and_tenancy() -> None:
    """验证SQLAlchemyRBAC往返及租户隔离对应的测试场景。"""
    engine, session_factory = create_async_session_factory()
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    repo = SQLAlchemyRbacRepository(session_factory)

    role = _role("r-sql-1", "t1", "support_admin")
    await repo.save_role(role)
    fetched = await repo.get_role("t1", "r-sql-1")
    assert fetched is not None
    assert fetched.name == "support_admin"
    assert fetched.permissions == ["ticket.read"]

    assert (
        await repo.get_role("t2", "r-sql-1") is None
    )  # 验证租户隔离，确保不同租户数据不会互相泄漏。
    assert [r.role_id for r in await repo.list_roles("t1")] == ["r-sql-1"]
    await engine.dispose()


async def test_sqlalchemy_role_and_assignment() -> None:
    """验证SQLAlchemy角色及分配对应的测试场景。"""
    engine, session_factory = create_async_session_factory()
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    repo = SQLAlchemyRbacRepository(session_factory)
    await repo.save_role(_role("r-asg", "t1", "support_admin"))
    assignment = RoleAssignment(
        assignment_id="a1",
        tenant_id="t1",
        user_id="user-1",
        role_id="r-asg",
    )
    await repo.save_assignment(assignment)

    mine = await repo.assignments_for_user("t1", "user-1")
    assert [a.role_id for a in mine] == ["r-asg"]
    assert await repo.assignments_for_user("t2", "user-1") == []
    await engine.dispose()
