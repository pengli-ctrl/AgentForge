from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentforge.platform.domain.audit import AuditEvent
from agentforge.platform.infrastructure.db.models import AuditEventRecord


class SQLAlchemyAuditRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def save(self, event: AuditEvent) -> None:
        async with self._session_factory() as session:
            session.add(AuditEventRecord.from_domain(event))
            await session.commit()

    async def list_events(
        self,
        tenant_id: str,
        limit: int = 100,
        resource_id: str | None = None,
    ) -> list[AuditEvent]:
        statement = select(AuditEventRecord).where(AuditEventRecord.tenant_id == tenant_id)
        if resource_id is not None:
            statement = statement.where(AuditEventRecord.resource_id == resource_id)
        statement = statement.order_by(AuditEventRecord.created_at.desc()).limit(limit)
        async with self._session_factory() as session:
            records = (await session.execute(statement)).scalars().all()
        return [record.to_domain() for record in records]

    async def query_events(
        self,
        tenant_id: str | None = None,
        action: str | None = None,
        actor_id: str | None = None,
        resource_id: str | None = None,
        resource_type: str | None = None,
        limit: int = 100,
        cursor: str | None = None,
    ) -> tuple[list[AuditEvent], str | None]:
        statement = select(AuditEventRecord)
        if tenant_id is not None:
            statement = statement.where(AuditEventRecord.tenant_id == tenant_id)
        if action is not None:
            statement = statement.where(AuditEventRecord.action == action)
        if actor_id is not None:
            statement = statement.where(AuditEventRecord.actor_id == actor_id)
        if resource_id is not None:
            statement = statement.where(AuditEventRecord.resource_id == resource_id)
        if resource_type is not None:
            statement = statement.where(AuditEventRecord.resource_type == resource_type)
        statement = statement.order_by(AuditEventRecord.created_at.desc())
        start = int(cursor) if (cursor is not None and cursor.isdigit()) else 0
        async with self._session_factory() as session:
            rows = (await session.execute(statement.offset(start).limit(limit + 1))).scalars().all()
        has_more = len(rows) > limit
        page = rows[:limit]
        next_cursor = str(start + len(page)) if has_more else None
        return [record.to_domain() for record in page], next_cursor
