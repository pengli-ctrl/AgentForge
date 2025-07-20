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
