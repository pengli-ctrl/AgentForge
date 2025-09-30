from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentforge.platform.domain.rbac import Role, RoleAssignment
from agentforge.platform.infrastructure.db.models import (
    RoleAssignmentRecord,
    RoleRecord,
)


class SQLAlchemyRbacRepository:
    """Async SQLAlchemy RBAC repository (roles + assignments)."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def save_role(self, role: Role) -> None:
        record = RoleRecord.from_domain(role)
        async with self._session_factory() as session:
            await session.merge(record)
            await session.commit()

    async def get_role(self, tenant_id: str, role_id: str) -> Role | None:
        async with self._session_factory() as session:
            record = await session.get(RoleRecord, role_id)
        if record is None or record.tenant_id != tenant_id:
            return None
        return record.to_domain()

    async def list_roles(self, tenant_id: str) -> list[Role]:
        statement = (
            select(RoleRecord)
            .where(RoleRecord.tenant_id == tenant_id)
            .order_by(RoleRecord.created_at.asc())
        )
        async with self._session_factory() as session:
            records = (await session.execute(statement)).scalars().all()
        return [record.to_domain() for record in records]

    async def save_assignment(self, assignment: RoleAssignment) -> None:
        record = RoleAssignmentRecord.from_domain(assignment)
        async with self._session_factory() as session:
            await session.merge(record)
            await session.commit()

    async def list_assignments(self, tenant_id: str) -> list[RoleAssignment]:
        statement = select(RoleAssignmentRecord).where(RoleAssignmentRecord.tenant_id == tenant_id)
        async with self._session_factory() as session:
            records = (await session.execute(statement)).scalars().all()
        return [record.to_domain() for record in records]

    async def assignments_for_user(
        self,
        tenant_id: str,
        user_id: str,
    ) -> list[RoleAssignment]:
        statement = select(RoleAssignmentRecord).where(
            RoleAssignmentRecord.tenant_id == tenant_id,
            RoleAssignmentRecord.user_id == user_id,
        )
        async with self._session_factory() as session:
            records = (await session.execute(statement)).scalars().all()
        return [record.to_domain() for record in records]
