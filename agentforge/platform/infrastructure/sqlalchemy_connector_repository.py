"""SQLAlchemy连接器仓储模块。"""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentforge.platform.domain.connector import ConnectorSpec
from agentforge.platform.infrastructure.db.models import ConnectorSpecRecord


class SQLAlchemyConnectorRepository:
    """SQLAlchemy连接器仓储，负责持久化读写。"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """初始化 SQLAlchemyConnectorRepository。

        Args:
            session_factory: 数据库会话工厂。
        """
        self._session_factory = session_factory

    async def save_spec(self, spec: ConnectorSpec) -> None:
        """保存规格。

        Args:
            spec: 资源规格定义。
        """
        record = ConnectorSpecRecord.from_domain(spec)
        async with self._session_factory() as session:
            await session.merge(record)
            await session.commit()

    async def get_spec(self, connector_id: str) -> ConnectorSpec | None:
        """获取规格。

        Args:
            connector_id: 连接器 ID。

        Returns:
            连接器规格无结果。
        """
        async with self._session_factory() as session:
            record = await session.get(ConnectorSpecRecord, connector_id)
        return record.to_domain() if record is not None else None

    async def list_specs(
        self,
        tenant_id: str | None = None,
        limit: int = 100,
    ) -> list[ConnectorSpec]:
        """查询规格。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            limit: 返回记录的最大数量。

        Returns:
            结果列表。
        """
        statement = select(ConnectorSpecRecord).order_by(ConnectorSpecRecord.created_at.desc())
        if tenant_id is not None:
            statement = statement.where(ConnectorSpecRecord.tenant_id == tenant_id)
        statement = statement.limit(limit)
        async with self._session_factory() as session:
            records = (await session.execute(statement)).scalars().all()
        return [record.to_domain() for record in records]

    async def delete_spec(self, connector_id: str) -> None:
        """删除规格。

        Args:
            connector_id: 连接器 ID。
        """
        statement = delete(ConnectorSpecRecord).where(
            ConnectorSpecRecord.connector_id == connector_id
        )
        async with self._session_factory() as session:
            await session.execute(statement)
            await session.commit()
