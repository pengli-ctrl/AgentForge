from __future__ import annotations

import builtins
from datetime import datetime

from sqlalchemy import delete as sql_delete
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
        archived: bool | None = None,
    ) -> list[ReportRun]:
        statement = select(ReportRunRecord).order_by(ReportRunRecord.generated_at.desc())
        if tenant_id is not None:
            statement = statement.where(ReportRunRecord.tenant_id == tenant_id)
        if report_type is not None:
            statement = statement.where(ReportRunRecord.report_type == report_type)
        if archived is not None:
            statement = statement.where(ReportRunRecord.archived == archived)
        statement = statement.limit(limit)
        async with self._session_factory() as session:
            records = (await session.execute(statement)).scalars().all()
        return [record.to_domain() for record in records]

    async def list_page(
        self,
        tenant_id: str | None = None,
        report_type: str | None = None,
        limit: int = 100,
        archived: bool | None = None,
        cursor: str | None = None,
    ) -> tuple[builtins.list[ReportRun], str | None]:
        statement = select(ReportRunRecord).order_by(ReportRunRecord.generated_at.desc())
        if tenant_id is not None:
            statement = statement.where(ReportRunRecord.tenant_id == tenant_id)
        if report_type is not None:
            statement = statement.where(ReportRunRecord.report_type == report_type)
        if archived is not None:
            statement = statement.where(ReportRunRecord.archived == archived)
        start = int(cursor) if (cursor is not None and cursor.isdigit()) else 0
        statement = statement.offset(start).limit(limit + 1)
        async with self._session_factory() as session:
            rows = (await session.execute(statement)).scalars().all()
        has_more = len(rows) > limit
        page = rows[:limit]
        next_cursor = str(start + len(page)) if has_more else None
        return [record.to_domain() for record in page], next_cursor

    async def set_archived(self, run_id: str, archived: bool) -> None:
        async with self._session_factory() as session:
            record = await session.get(ReportRunRecord, run_id)
            if record is None:
                raise KeyError(run_id)
            record.archived = archived
            await session.commit()

    async def delete_older_than(
        self,
        cutoff: datetime,
        tenant_id: str | None = None,
        include_archived: bool = False,
    ) -> int:
        statement = sql_delete(ReportRunRecord).where(ReportRunRecord.generated_at < cutoff)
        if tenant_id is not None:
            statement = statement.where(ReportRunRecord.tenant_id == tenant_id)
        if not include_archived:
            statement = statement.where(ReportRunRecord.archived.is_(False))
        async with self._session_factory() as session:
            # count matching first, then delete, for a stable removed count
            select_ids = (
                select(ReportRunRecord.run_id)
                .where(ReportRunRecord.generated_at < cutoff)
                .order_by(ReportRunRecord.generated_at.desc())
            )
            if tenant_id is not None:
                select_ids = select_ids.where(ReportRunRecord.tenant_id == tenant_id)
            if not include_archived:
                select_ids = select_ids.where(ReportRunRecord.archived.is_(False))
            rows = (await session.execute(select_ids)).scalars().all()
            if rows:
                await session.execute(statement)
            await session.commit()
        return len(rows)
