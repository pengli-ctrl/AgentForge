from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentforge.platform.domain.reporting import ReportRun
from agentforge.platform.infrastructure.db.models import ReportRunRecord


class SQLAlchemyReportRunRepository:
    """Async SQLAlchemy persisted report run repository."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def save(self, run: ReportRun) -> None:
        record = ReportRunRecord.from_domain(run)
        async with self._session_factory() as session:
            await session.merge(record)
            await session.commit()

    async def get(self, run_id: str) -> ReportRun | None:
        async with self._session_factory() as session:
            record = await session.get(ReportRunRecord, run_id)
        if record is None:
            return None
        return record.to_domain()

    async def list(
        self,
        tenant_id: str | None = None,
        report_type: str | None = None,
        limit: int = 100,
    ) -> list[ReportRun]:
        statement = select(ReportRunRecord).order_by(ReportRunRecord.generated_at.desc())
        if tenant_id is not None:
            statement = statement.where(ReportRunRecord.tenant_id == tenant_id)
        if report_type is not None:
            statement = statement.where(ReportRunRecord.report_type == report_type)
        statement = statement.limit(limit)
        async with self._session_factory() as session:
            records = (await session.execute(statement)).scalars().all()
        return [record.to_domain() for record in records]
