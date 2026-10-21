"""SQLAlchemy报告仓储模块。"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete as sql_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentforge.platform.domain.reporting import ScheduledReport
from agentforge.platform.infrastructure.db.models import ScheduledReportRecord


class SQLAlchemyScheduledReportRepository:
    """报告仓储，负责持久化读写。"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """初始化 SQLAlchemyScheduledReportRepository。

        Args:
            session_factory: 数据库会话工厂。
        """
        self._session_factory = session_factory

    async def save(self, report: ScheduledReport) -> None:
        """保存报告。

        Args:
            report: 报告。
        """
        record = ScheduledReportRecord.from_domain(report)
        async with self._session_factory() as session:
            await session.merge(record)
            await session.commit()

    async def get(self, report_id: str) -> ScheduledReport | None:
        """获取报告。

        Args:
            report_id: 报告 ID。

        Returns:
            报告无结果。
        """
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
        """查询调度。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            limit: 返回记录的最大数量。

        Returns:
            结果列表。
        """
        statement = select(ScheduledReportRecord).order_by(ScheduledReportRecord.created_at.asc())
        if tenant_id is not None:
            statement = statement.where(ScheduledReportRecord.tenant_id == tenant_id)
        statement = statement.limit(limit)
        async with self._session_factory() as session:
            records = (await session.execute(statement)).scalars().all()
        return [record.to_domain() for record in records]

    async def delete(self, report_id: str) -> None:
        """删除报告。

        Args:
            report_id: 报告 ID。
        """
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
        """查询到期。

        Args:
            before: 之前。
            limit: 返回记录的最大数量。

        Returns:
            结果列表。
        """
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
