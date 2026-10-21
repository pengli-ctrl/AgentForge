"""SQLAlchemy租户配额仓储模块。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentforge.platform.domain.tenant_quota import TenantQuota
from agentforge.platform.infrastructure.db.models import TenantQuotaRecord


class SQLAlchemyTenantQuotaRepository:
    """租户配额仓储，负责持久化读写。"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """初始化 SQLAlchemyTenantQuotaRepository。

        Args:
            session_factory: 数据库会话工厂。
        """
        self._session_factory = session_factory

    async def upsert(self, quota: TenantQuota) -> None:
        """新建或更新租户配额。

        Args:
            quota: 配额配置。
        """
        record = TenantQuotaRecord.from_domain(quota)
        async with self._session_factory() as session:
            await session.merge(record)
            await session.commit()

    async def get(self, tenant_id: str) -> TenantQuota | None:
        """读取租户配额。

        Args:
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            租户配额无结果。
        """
        async with self._session_factory() as session:
            record = await session.get(TenantQuotaRecord, tenant_id)
        if record is None:
            return None
        return record.to_domain()

    async def list(self, limit: int = 100) -> list[TenantQuota]:
        """查询租户配额。

        Args:
            limit: 返回记录的最大数量。

        Returns:
            结果列表。
        """
        statement = (
            select(TenantQuotaRecord).order_by(TenantQuotaRecord.updated_at.asc()).limit(limit)
        )
        async with self._session_factory() as session:
            records = (await session.execute(statement)).scalars().all()
        return [record.to_domain() for record in records]

    async def delete(self, tenant_id: str) -> None:
        """删除租户配额。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
        """
        async with self._session_factory() as session:
            record = await session.get(TenantQuotaRecord, tenant_id)
            if record is not None:
                await session.delete(record)
                await session.commit()
