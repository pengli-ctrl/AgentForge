"""AgentForge 平台基础设施层：sqlalchemy_scheduled_report_repository。

本模块提供 sqlalchemy_scheduled_report_repository 的数据库持久化实现，负责事务、查询、租户隔离和一致性约束。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：SQLAlchemyScheduledReportRepository。
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete as sql_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentforge.platform.domain.reporting import ScheduledReport
from agentforge.platform.infrastructure.db.models import ScheduledReportRecord


class SQLAlchemyScheduledReportRepository:
    """SQLAlchemyScheduledReportRepository。

    SQLAlchemyScheduledReportRepository 负责数据读写，并确保租户隔离、事务一致性和持久化细节不泄漏到应用层。

    主要成员：
    - 方法 save()。
    - 方法 get()。
    - 方法 list_schedules()。
    - 方法 delete()。
    - 方法 list_due()。

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

    async def save(self, report: ScheduledReport) -> None:
        """执行 save 对应的核心操作，并保持调用契约稳定。

        Args:
            report: ScheduledReport，调用方传入的 report 参数。

        Returns:
            None，函数执行后的结果。
        """
        record = ScheduledReportRecord.from_domain(report)
        async with self._session_factory() as session:
            await session.merge(record)
            await session.commit()

    async def get(self, report_id: str) -> ScheduledReport | None:
        """执行 get 对应的核心操作，并保持调用契约稳定。

        Args:
            report_id: str，调用方传入的 report_id 参数。

        Returns:
            ScheduledReport | None，函数执行后的结果。
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
        """查询并返回列表结果，并返回调用方需要的结果。

        Args:
            tenant_id: str | None，调用方传入的 tenant_id 参数。
            limit: int，调用方传入的 limit 参数。

        Returns:
            list[ScheduledReport]，函数执行后的结果。
        """
        statement = select(ScheduledReportRecord).order_by(ScheduledReportRecord.created_at.asc())
        if tenant_id is not None:
            statement = statement.where(ScheduledReportRecord.tenant_id == tenant_id)
        statement = statement.limit(limit)
        async with self._session_factory() as session:
            records = (await session.execute(statement)).scalars().all()
        return [record.to_domain() for record in records]

    async def delete(self, report_id: str) -> None:
        """执行 delete 对应的核心操作，并保持调用契约稳定。

        Args:
            report_id: str，调用方传入的 report_id 参数。

        Returns:
            None，函数执行后的结果。
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
        """查询并返回列表结果，并返回调用方需要的结果。

        Args:
            before: datetime | None，调用方传入的 before 参数。
            limit: int，调用方传入的 limit 参数。

        Returns:
            list[ScheduledReport]，函数执行后的结果。
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
