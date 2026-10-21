"""SQLAlchemy租户仓储模块。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentforge.platform.domain.tenant_account import TenantAccount, TenantStatus
from agentforge.platform.infrastructure.db.tenant_account_model import TenantAccountRecord


class SQLAlchemyTenantAccountRepository:
    """租户账户仓储，负责持久化读写。"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """初始化 SQLAlchemyTenantAccountRepository。

        Args:
            session_factory: 数据库会话工厂。
        """
        self._session_factory = session_factory

    async def save(self, account: TenantAccount) -> None:
        """保存租户账户。

        Args:
            account: 租户账户。
        """
        record = TenantAccountRecord(
            tenant_id=account.tenant_id,
            name=account.name,
            plan_name=account.plan_name,
            status=account.status.value,
            created_at=account.created_at,
            updated_at=account.updated_at,
            suspended_at=account.suspended_at,
            cancelled_at=account.cancelled_at,
            status_reason=account.status_reason,
        )
        async with self._session_factory() as session:
            await session.merge(record)
            await session.commit()

    async def get(self, tenant_id: str) -> TenantAccount | None:
        """读取租户账户。

        Args:
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            租户无结果。
        """
        async with self._session_factory() as session:
            record = await session.get(TenantAccountRecord, tenant_id)
        return self._to_domain(record) if record is not None else None

    async def list(self, limit: int = 100) -> list[TenantAccount]:
        """查询租户账户。

        Args:
            limit: 返回记录的最大数量。

        Returns:
            结果列表。
        """
        statement = (
            select(TenantAccountRecord).order_by(TenantAccountRecord.created_at.desc()).limit(limit)
        )
        async with self._session_factory() as session:
            records = list((await session.execute(statement)).scalars().all())
        return [self._to_domain(record) for record in records]

    @staticmethod
    def _to_domain(record: TenantAccountRecord) -> TenantAccount:
        """转换领域。

        Args:
            record: 待处理的领域记录。

        Returns:
            租户结果。
        """
        return TenantAccount(
            tenant_id=record.tenant_id,
            name=record.name,
            plan_name=record.plan_name,
            status=TenantStatus(record.status),
            created_at=record.created_at,
            updated_at=record.updated_at,
            suspended_at=record.suspended_at,
            cancelled_at=record.cancelled_at,
            status_reason=record.status_reason,
        )


__all__ = ["SQLAlchemyTenantAccountRepository"]
