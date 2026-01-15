"""AgentForge 平台基础设施层：sqlalchemy_tenant_quota_repository。

本模块提供 sqlalchemy_tenant_quota_repository 的数据库持久化实现，负责事务、查询、租户隔离和一致性约束。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：SQLAlchemyTenantQuotaRepository。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentforge.platform.domain.tenant_quota import TenantQuota
from agentforge.platform.infrastructure.db.models import TenantQuotaRecord


class SQLAlchemyTenantQuotaRepository:
    """SQLAlchemyTenantQuotaRepository。

    SQLAlchemyTenantQuotaRepository 负责数据读写，并确保租户隔离、事务一致性和持久化细节不泄漏到应用层。

    主要成员：
    - 方法 upsert()。
    - 方法 get()。
    - 方法 list()。
    - 方法 delete()。

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

    async def upsert(self, quota: TenantQuota) -> None:
        """执行 upsert 对应的逻辑，并返回处理结果。

        Args:
            quota: TenantQuota，调用方传入的 quota 参数。

        Returns:
            None，函数执行后的结果。
        """
        record = TenantQuotaRecord.from_domain(quota)
        async with self._session_factory() as session:
            await session.merge(record)
            await session.commit()

    async def get(self, tenant_id: str) -> TenantQuota | None:
        """执行 get 对应的核心操作，并保持调用契约稳定。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。

        Returns:
            TenantQuota | None，函数执行后的结果。
        """
        async with self._session_factory() as session:
            record = await session.get(TenantQuotaRecord, tenant_id)
        if record is None:
            return None
        return record.to_domain()

    async def list(self, limit: int = 100) -> list[TenantQuota]:
        """执行 list 对应的核心操作，并保持调用契约稳定。

        Args:
            limit: int，调用方传入的 limit 参数。

        Returns:
            list[TenantQuota]，函数执行后的结果。
        """
        statement = (
            select(TenantQuotaRecord).order_by(TenantQuotaRecord.updated_at.asc()).limit(limit)
        )
        async with self._session_factory() as session:
            records = (await session.execute(statement)).scalars().all()
        return [record.to_domain() for record in records]

    async def delete(self, tenant_id: str) -> None:
        """执行 delete 对应的核心操作，并保持调用契约稳定。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。

        Returns:
            None，函数执行后的结果。
        """
        async with self._session_factory() as session:
            record = await session.get(TenantQuotaRecord, tenant_id)
            if record is not None:
                await session.delete(record)
                await session.commit()
