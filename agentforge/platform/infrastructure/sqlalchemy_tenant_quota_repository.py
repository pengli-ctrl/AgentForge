from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentforge.platform.domain.tenant_quota import TenantQuota
from agentforge.platform.infrastructure.db.models import TenantQuotaRecord


class SQLAlchemyTenantQuotaRepository:
    """Async SQLAlchemy per-tenant quota repository."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def upsert(self, quota: TenantQuota) -> None:
        record = TenantQuotaRecord.from_domain(quota)
        async with self._session_factory() as session:
            await session.merge(record)
            await session.commit()

    async def get(self, tenant_id: str) -> TenantQuota | None:
        async with self._session_factory() as session:
            record = await session.get(TenantQuotaRecord, tenant_id)
        if record is None:
            return None
        return record.to_domain()

    async def list(self, limit: int = 100) -> list[TenantQuota]:
        statement = (
            select(TenantQuotaRecord).order_by(TenantQuotaRecord.updated_at.asc()).limit(limit)
        )
        async with self._session_factory() as session:
            records = (await session.execute(statement)).scalars().all()
        return [record.to_domain() for record in records]

    async def delete(self, tenant_id: str) -> None:
        async with self._session_factory() as session:
            record = await session.get(TenantQuotaRecord, tenant_id)
            if record is not None:
                await session.delete(record)
                await session.commit()
