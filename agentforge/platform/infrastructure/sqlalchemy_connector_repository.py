"""AgentForge 平台基础设施层：sqlalchemy_connector_repository。

本模块提供 sqlalchemy_connector_repository 的数据库持久化实现，负责事务、查询、租户隔离和一致性约束。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：SQLAlchemyConnectorRepository。
"""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentforge.platform.domain.connector import ConnectorSpec
from agentforge.platform.infrastructure.db.models import ConnectorSpecRecord


class SQLAlchemyConnectorRepository:
    """SQLAlchemyConnectorRepository。

    SQLAlchemyConnectorRepository 负责数据读写，并确保租户隔离、事务一致性和持久化细节不泄漏到应用层。

    主要成员：
    - 方法 save_spec()。
    - 方法 get_spec()。
    - 方法 list_specs()。
    - 方法 delete_spec()。

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

    async def save_spec(self, spec: ConnectorSpec) -> None:
        """保存业务数据，并返回调用方需要的结果。

        Args:
            spec: ConnectorSpec，调用方传入的 spec 参数。

        Returns:
            None，函数执行后的结果。
        """
        record = ConnectorSpecRecord.from_domain(spec)
        async with self._session_factory() as session:
            await session.merge(record)
            await session.commit()

    async def get_spec(self, connector_id: str) -> ConnectorSpec | None:
        """读取并返回指定数据，并返回调用方需要的结果。

        Args:
            connector_id: str，调用方传入的 connector_id 参数。

        Returns:
            ConnectorSpec | None，函数执行后的结果。
        """
        async with self._session_factory() as session:
            record = await session.get(ConnectorSpecRecord, connector_id)
        return record.to_domain() if record is not None else None

    async def list_specs(
        self,
        tenant_id: str | None = None,
        limit: int = 100,
    ) -> list[ConnectorSpec]:
        """查询并返回列表结果，并返回调用方需要的结果。

        Args:
            tenant_id: str | None，调用方传入的 tenant_id 参数。
            limit: int，调用方传入的 limit 参数。

        Returns:
            list[ConnectorSpec]，函数执行后的结果。
        """
        statement = select(ConnectorSpecRecord).order_by(ConnectorSpecRecord.created_at.desc())
        if tenant_id is not None:
            statement = statement.where(ConnectorSpecRecord.tenant_id == tenant_id)
        statement = statement.limit(limit)
        async with self._session_factory() as session:
            records = (await session.execute(statement)).scalars().all()
        return [record.to_domain() for record in records]

    async def delete_spec(self, connector_id: str) -> None:
        """删除指定数据，并返回调用方需要的结果。

        Args:
            connector_id: str，调用方传入的 connector_id 参数。

        Returns:
            None，函数执行后的结果。
        """
        statement = delete(ConnectorSpecRecord).where(
            ConnectorSpecRecord.connector_id == connector_id
        )
        async with self._session_factory() as session:
            await session.execute(statement)
            await session.commit()
