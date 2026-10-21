"""SQLAlchemy租户模块仓储模块。"""

from __future__ import annotations

from copy import deepcopy
from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentforge.platform.domain.tenant_module import ConfigSource, TenantModuleConfig
from agentforge.platform.infrastructure.db.tenant_module_model import TenantModuleRecord


class SQLAlchemyTenantModuleRepository:
    """租户模块仓储，负责持久化读写。"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """初始化 SQLAlchemyTenantModuleRepository。

        Args:
            session_factory: 数据库会话工厂。
        """
        self._session_factory = session_factory

    async def get(self, tenant_id: str, module_name: str) -> TenantModuleConfig | None:
        """读取租户模块。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            module_name: 模块名称。

        Returns:
            租户模块配置无结果。
        """
        async with self._session_factory() as session:
            record = await session.get(TenantModuleRecord, (tenant_id, module_name))
            return self._to_domain(record) if record is not None else None

    async def list(self, tenant_id: str) -> list[TenantModuleConfig]:
        """查询租户模块。

        Args:
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            结果列表。
        """
        statement = (
            select(TenantModuleRecord)
            .where(TenantModuleRecord.tenant_id == tenant_id)
            .order_by(TenantModuleRecord.module_name)
        )
        async with self._session_factory() as session:
            records = list((await session.execute(statement)).scalars().all())
        return [self._to_domain(record) for record in records]

    async def save(self, state: TenantModuleConfig) -> None:
        """保存租户模块。

        Args:
            state: 当前状态。
        """
        async with self._session_factory() as session:
            key = (state.tenant_id, state.module_name)
            record = await session.get(TenantModuleRecord, key)
            if record is None:
                record = TenantModuleRecord(
                    tenant_id=state.tenant_id, module_name=state.module_name
                )
                session.add(record)
            record.enabled = state.enabled
            record.plan_name = state.plan_name
            record.config_version = state.config_version
            record.source = state.source
            record.updated_by = state.updated_by
            record.config_values = deepcopy(state.values)
            record.secret_refs = deepcopy(state.secret_refs)
            record.updated_at = state.updated_at
            await session.commit()

    @staticmethod
    def _to_domain(record: TenantModuleRecord) -> TenantModuleConfig:
        """转换领域。

        Args:
            record: 待处理的领域记录。

        Returns:
            租户模块配置结果。
        """
        return TenantModuleConfig(
            tenant_id=record.tenant_id,
            module_name=record.module_name,
            enabled=record.enabled,
            config_version=record.config_version,
            source=cast(ConfigSource, record.source),
            updated_by=record.updated_by,
            plan_name=record.plan_name,
            updated_at=record.updated_at,
            values=deepcopy(record.config_values or {}),
            secret_refs=deepcopy(record.secret_refs or {}),
        )
