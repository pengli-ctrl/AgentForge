from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete as sql_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentforge.platform.domain.reporting import ScheduledReport
from agentforge.platform.infrastructure.db.models import ScheduledReportRecord


class SQLAlchemyScheduledReportRepository:
    """Async SQLAlchemy scheduled report repository."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def save(self, report: ScheduledReport) -> None:
        record = ScheduledReportRecord.from_domain(report)
        async with self._session_factory() as session:
            await session.merge(record)
            await session.commit()

    async def get(self, report_id: str) -> ScheduledReport | None:
        async with self._session_factory() as session:
            record = await session.get(ScheduledReportRecord, report_id)
        if record is None:
            return None
        return record.to_domain()

    async def list_schedules(
        self,
        tenant_id: str | None = None,
        limit: int = 100,
    ) -> list[ScheduledReport]:
        statement = select(ScheduledReportRecord).order_by(ScheduledReportRecord.created_at.asc())
        if tenant_id is not None:
            statement = statement.where(ScheduledReportRecord.tenant_id == tenant_id)
        statement = statement.limit(limit)
        async with self._session_factory() as session:
            records = (await session.execute(statement)).scalars().all()
        return [record.to_domain() for record in records]

    async def delete(self, report_id: str) -> None:
        async with self._session_factory() as session:
            await session.execute(
                sql_delete(ScheduledReportRecord).where(
                    ScheduledReportRecord.report_id == report_id
                )
            )
            await session.commit()

    async def list_due(
        self,
        before: datetime | None = None,
        limit: int = 100,
    ) -> list[ScheduledReport]:
        statement = (
            select(ScheduledReportRecord)
            .where(ScheduledReportRecord.enabled.is_(True))
            .where(ScheduledReportRecord.next_run_at <= (before or datetime.now(timezone.utc)))
            .order_by(ScheduledReportRecord.next_run_at.asc())
            .limit(limit)
        )
        async with self._session_factory() as session:
            records = (await session.execute(statement)).scalars().all()
        return [record.to_domain() for record in records]
