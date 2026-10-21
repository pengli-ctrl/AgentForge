"""SQLAlchemyRBAC仓储模块。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentforge.platform.domain.rbac import Role, RoleAssignment
from agentforge.platform.infrastructure.db.models import RoleAssignmentRecord, RoleRecord


class SQLAlchemyRbacRepository:
    """RBAC仓储，负责持久化读写。"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """初始化 SQLAlchemyRbacRepository。

        Args:
            session_factory: 数据库会话工厂。
        """
        self._session_factory = session_factory

    async def save_role(self, role: Role) -> None:
        """保存角色。

        Args:
            role: 角色。
        """
        record = RoleRecord.from_domain(role)
        async with self._session_factory() as session:
            await session.merge(record)
            await session.commit()

    async def get_role(self, tenant_id: str, role_id: str) -> Role | None:
        """读取角色。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            role_id: 角色 ID。

        Returns:
            角色无结果。
        """
        async with self._session_factory() as session:
            record = await session.get(RoleRecord, role_id)
        if record is None or record.tenant_id != tenant_id:
            return None
        return record.to_domain()

    async def list_roles(self, tenant_id: str) -> list[Role]:
        """查询角色。

        Args:
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            结果列表。
        """
        statement = (
            select(RoleRecord)
            .where(RoleRecord.tenant_id == tenant_id)
            .order_by(RoleRecord.created_at.asc())
        )
        async with self._session_factory() as session:
            records = (await session.execute(statement)).scalars().all()
        return [record.to_domain() for record in records]

    async def save_assignment(self, assignment: RoleAssignment) -> None:
        """保存分配。

        Args:
            assignment: 分配。
        """
        record = RoleAssignmentRecord.from_domain(assignment)
        async with self._session_factory() as session:
            await session.merge(record)
            await session.commit()

    async def list_assignments(self, tenant_id: str) -> list[RoleAssignment]:
        """查询分配记录。

        Args:
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            结果列表。
        """
        statement = select(RoleAssignmentRecord).where(RoleAssignmentRecord.tenant_id == tenant_id)
        async with self._session_factory() as session:
            records = (await session.execute(statement)).scalars().all()
        return [record.to_domain() for record in records]

    async def assignments_for_user(
        self,
        tenant_id: str,
        user_id: str,
    ) -> list[RoleAssignment]:
        """获取用户的分配记录。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            user_id: 用户 ID。

        Returns:
            结果列表。
        """
        statement = select(RoleAssignmentRecord).where(
            RoleAssignmentRecord.tenant_id == tenant_id,
            RoleAssignmentRecord.user_id == user_id,
        )
        async with self._session_factory() as session:
            records = (await session.execute(statement)).scalars().all()
        return [record.to_domain() for record in records]
