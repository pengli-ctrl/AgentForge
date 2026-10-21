"""SQLAlchemy报告运行仓储模块。"""

from __future__ import annotations

import builtins
from datetime import datetime

from sqlalchemy import and_
from sqlalchemy import delete as sql_delete
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentforge.platform.domain.reporting import ReportRun, _decode_run_cursor, _encode_run_cursor
from agentforge.platform.infrastructure.db.models import ReportRunRecord


class SQLAlchemyReportRunRepository:
    """报告运行仓储，负责持久化读写。"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """初始化 SQLAlchemyReportRunRepository。

        Args:
            session_factory: 数据库会话工厂。
        """
        self._session_factory = session_factory

    async def save(self, run: ReportRun) -> None:
        """保存报告运行。

        Args:
            run: 运行。
        """
        record = ReportRunRecord.from_domain(run)
        async with self._session_factory() as session:
            await session.merge(record)
            await session.commit()

    async def get(self, run_id: str) -> ReportRun | None:
        """获取报告运行。

        Args:
            run_id: 运行记录 ID。

        Returns:
            报告运行无结果。
        """
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
        """查询报告运行。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            report_type: 报告类型。
            limit: 返回记录的最大数量。
            archived: 已归档。

        Returns:
            结果列表。
        """
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
        """查询页面。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            report_type: 报告类型。
            limit: 返回记录的最大数量。
            archived: 已归档。
            cursor: 分页游标。

        Returns:
            结果元组。
        """
        statement = select(ReportRunRecord).order_by(
            ReportRunRecord.generated_at.desc(),
            ReportRunRecord.run_id.desc(),
        )
        if tenant_id is not None:
            statement = statement.where(ReportRunRecord.tenant_id == tenant_id)
        if report_type is not None:
            statement = statement.where(ReportRunRecord.report_type == report_type)
        if archived is not None:
            statement = statement.where(ReportRunRecord.archived == archived)
        anchor = _decode_run_cursor(cursor)
        if anchor is not None:
            anchor_ts, anchor_id = anchor
            statement = statement.where(
                or_(
                    ReportRunRecord.generated_at < anchor_ts,
                    and_(
                        ReportRunRecord.generated_at == anchor_ts,
                        ReportRunRecord.run_id < anchor_id,
                    ),
                )
            )
        statement = statement.limit(limit + 1)
        async with self._session_factory() as session:
            rows = (await session.execute(statement)).scalars().all()
        page = rows[:limit]
        next_cursor = (
            _encode_run_cursor(page[-1].generated_at, page[-1].run_id)
            if len(rows) > limit
            else None
        )
        return [record.to_domain() for record in page], next_cursor

    async def set_archived(self, run_id: str, archived: bool) -> None:
        """设置已归档。

        Args:
            run_id: 运行记录 ID。
            archived: 已归档。

        Raises:
            KeyError: 缺少必要配置或目标对象时抛出。
        """
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
        """删除更旧比。

        Args:
            cutoff: 截止时间。
            tenant_id: 租户 ID，用于数据隔离。
            include_archived: 已归档。

        Returns:
            整数结果。
        """
        statement = sql_delete(ReportRunRecord).where(ReportRunRecord.generated_at <= cutoff)
        if tenant_id is not None:
            statement = statement.where(ReportRunRecord.tenant_id == tenant_id)
        if not include_archived:
            statement = statement.where(ReportRunRecord.archived.is_(False))
        async with self._session_factory() as session:
            select_ids = (
                select(ReportRunRecord.run_id)
                .where(ReportRunRecord.generated_at <= cutoff)
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
