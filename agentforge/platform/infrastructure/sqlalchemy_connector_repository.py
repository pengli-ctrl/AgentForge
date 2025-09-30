from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentforge.platform.domain.connector import ConnectorSpec
from agentforge.platform.infrastructure.db.models import ConnectorSpecRecord


class SQLAlchemyConnectorRepository:
    """Async SQLAlchemy connector spec repository."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def save_spec(self, spec: ConnectorSpec) -> None:
        record = ConnectorSpecRecord.from_domain(spec)
        async with self._session_factory() as session:
            await session.merge(record)
            await session.commit()

    async def get_spec(self, connector_id: str) -> ConnectorSpec | None:
        async with self._session_factory() as session:
            record = await session.get(ConnectorSpecRecord, connector_id)
        return record.to_domain() if record is not None else None

    async def list_specs(
        self,
        tenant_id: str | None = None,
        limit: int = 100,
    ) -> list[ConnectorSpec]:
        statement = select(ConnectorSpecRecord).order_by(ConnectorSpecRecord.created_at.desc())
        if tenant_id is not None:
            statement = statement.where(ConnectorSpecRecord.tenant_id == tenant_id)
        statement = statement.limit(limit)
        async with self._session_factory() as session:
            records = (await session.execute(statement)).scalars().all()
        return [record.to_domain() for record in records]

    async def delete_spec(self, connector_id: str) -> None:
        statement = delete(ConnectorSpecRecord).where(
            ConnectorSpecRecord.connector_id == connector_id
        )
        async with self._session_factory() as session:
            await session.execute(statement)
            await session.commit()
