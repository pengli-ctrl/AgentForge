from __future__ import annotations

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from agentforge.platform.domain.rbac import Role, RoleAssignment
from agentforge.platform.infrastructure.db.base import Base
from agentforge.platform.infrastructure.memory_rbac_repository import MemoryRbacRepository
from agentforge.platform.infrastructure.sqlalchemy_rbac_repository import (
    SQLAlchemyRbacRepository,
)


def create_async_session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    return engine, async_sessionmaker(engine, expire_on_commit=False)


def _role(role_id: str, tenant_id: str, name: str) -> Role:
    return Role(
        role_id=role_id,
        tenant_id=tenant_id,
        name=name,
        description="test role",
        permissions=["ticket.read"],
        built_in=False,
    )


async def test_memory_rbac_roundtrip_and_tenancy() -> None:
    repo = MemoryRbacRepository()
    await repo.save_role(_role("r1", "t1", "support_admin"))
    await repo.save_role(_role("r2", "t2", "support_agent"))

    assert (await repo.get_role("t1", "r1")) is not None
    assert await repo.get_role("t1", "r2") is None  # tenant isolation
    assert [r.role_id for r in await repo.list_roles("t1")] == ["r1"]


async def test_sqlalchemy_rbac_roundtrip_and_tenancy() -> None:
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

    assert await repo.get_role("t2", "r-sql-1") is None  # tenant isolation
    assert [r.role_id for r in await repo.list_roles("t1")] == ["r-sql-1"]
    await engine.dispose()


async def test_sqlalchemy_role_and_assignment() -> None:
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
