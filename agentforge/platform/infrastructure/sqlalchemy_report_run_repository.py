"""AgentForge 平台基础设施层：sqlalchemy_report_run_repository。

本模块提供 sqlalchemy_report_run_repository 的数据库持久化实现，负责事务、查询、租户隔离和一致性约束。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：SQLAlchemyReportRunRepository。
"""

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
    """SQLAlchemyReportRunRepository。

    SQLAlchemyReportRunRepository 负责数据读写，并确保租户隔离、事务一致性和持久化细节不泄漏到应用层。

    主要成员：
    - 方法 save()。
    - 方法 get()。
    - 方法 list()。
    - 方法 list_page()。
    - 方法 set_archived()。
    - 方法 delete_older_than()。

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

    async def save(self, run: ReportRun) -> None:
        """执行 save 对应的核心操作，并保持调用契约稳定。

        Args:
            run: ReportRun，调用方传入的 run 参数。

        Returns:
            None，函数执行后的结果。
        """
        record = ReportRunRecord.from_domain(run)
        async with self._session_factory() as session:
            await session.merge(record)
            await session.commit()

    async def get(self, run_id: str) -> ReportRun | None:
        """执行 get 对应的核心操作，并保持调用契约稳定。

        Args:
            run_id: str，调用方传入的 run_id 参数。

        Returns:
            ReportRun | None，函数执行后的结果。
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
        """执行 list 对应的核心操作，并保持调用契约稳定。

        Args:
            tenant_id: str | None，调用方传入的 tenant_id 参数。
            report_type: str | None，调用方传入的 report_type 参数。
            limit: int，调用方传入的 limit 参数。
            archived: bool | None，调用方传入的 archived 参数。

        Returns:
            list[ReportRun]，函数执行后的结果。
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
        """查询并返回列表结果，并返回调用方需要的结果。

        Args:
            tenant_id: str | None，调用方传入的 tenant_id 参数。
            report_type: str | None，调用方传入的 report_type 参数。
            limit: int，调用方传入的 limit 参数。
            archived: bool | None，调用方传入的 archived 参数。
            cursor: str | None，调用方传入的 cursor 参数。

        Returns:
            tuple[builtins.list[ReportRun], str | None]，函数执行后的结果。
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
        """执行 set_archived 对应的逻辑，并返回处理结果。

        Args:
            run_id: str，调用方传入的 run_id 参数。
            archived: bool，调用方传入的 archived 参数。

        Returns:
            None，函数执行后的结果。

        Raises:
            KeyError: 当输入、状态或外部依赖不满足要求时抛出。
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
        """删除指定数据，并返回调用方需要的结果。

        Args:
            cutoff: datetime，调用方传入的 cutoff 参数。
            tenant_id: str | None，调用方传入的 tenant_id 参数。
            include_archived: bool，调用方传入的 include_archived 参数。

        Returns:
            int，函数执行后的结果。
        """
        statement = sql_delete(ReportRunRecord).where(ReportRunRecord.generated_at < cutoff)
        if tenant_id is not None:
            statement = statement.where(ReportRunRecord.tenant_id == tenant_id)
        if not include_archived:
            statement = statement.where(ReportRunRecord.archived.is_(False))
        async with self._session_factory() as session:
            # 说明：该步骤用于保证业务流程、租户隔离和可追踪性。
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
