"""AgentForge 平台基础设施层：sqlalchemy_rbac_repository。

本模块提供 sqlalchemy_rbac_repository 的数据库持久化实现，负责事务、查询、租户隔离和一致性约束。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：SQLAlchemyRbacRepository。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentforge.platform.domain.rbac import Role, RoleAssignment
from agentforge.platform.infrastructure.db.models import (
    RoleAssignmentRecord,
    RoleRecord,
)


class SQLAlchemyRbacRepository:
    """SQLAlchemyRbacRepository。

    SQLAlchemyRbacRepository 负责数据读写，并确保租户隔离、事务一致性和持久化细节不泄漏到应用层。

    主要成员：
    - 方法 save_role()。
    - 方法 get_role()。
    - 方法 list_roles()。
    - 方法 save_assignment()。
    - 方法 list_assignments()。
    - 方法 assignments_for_user()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Args:
            session_factory: async_sessionmaker[AsyncSession]，调用方传入的 session_factory 参数。

        Returns:
            None，函数执行后的结果。
        """
        self._session_factory = session_factory

    async def save_role(self, role: Role) -> None:
        """保存业务数据，并返回调用方需要的结果。

        Args:
            role: Role，调用方传入的 role 参数。

        Returns:
            None，函数执行后的结果。
        """
        record = RoleRecord.from_domain(role)
        async with self._session_factory() as session:
            await session.merge(record)
            await session.commit()

    async def get_role(self, tenant_id: str, role_id: str) -> Role | None:
        """读取并返回指定数据，并返回调用方需要的结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。
            role_id: str，调用方传入的 role_id 参数。

        Returns:
            Role | None，函数执行后的结果。
        """
        async with self._session_factory() as session:
            record = await session.get(RoleRecord, role_id)
        if record is None or record.tenant_id != tenant_id:
            return None
        return record.to_domain()

    async def list_roles(self, tenant_id: str) -> list[Role]:
        """查询并返回列表结果，并返回调用方需要的结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。

        Returns:
            list[Role]，函数执行后的结果。
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
        """保存业务数据，并返回调用方需要的结果。

        Args:
            assignment: RoleAssignment，调用方传入的 assignment 参数。

        Returns:
            None，函数执行后的结果。
        """
        record = RoleAssignmentRecord.from_domain(assignment)
        async with self._session_factory() as session:
            await session.merge(record)
            await session.commit()

    async def list_assignments(self, tenant_id: str) -> list[RoleAssignment]:
        """查询并返回列表结果，并返回调用方需要的结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。

        Returns:
            list[RoleAssignment]，函数执行后的结果。
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
        """执行 assignments_for_user 对应的逻辑，并返回处理结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。
            user_id: str，调用方传入的 user_id 参数。

        Returns:
            list[RoleAssignment]，函数执行后的结果。
        """
        statement = select(RoleAssignmentRecord).where(
            RoleAssignmentRecord.tenant_id == tenant_id,
            RoleAssignmentRecord.user_id == user_id,
        )
        async with self._session_factory() as session:
            records = (await session.execute(statement)).scalars().all()
        return [record.to_domain() for record in records]
