"""SQLAlchemy写回任务仓储模块。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentforge.platform.modules.expense.domain.writeback_job import ExpenseWritebackJob
from agentforge.platform.modules.expense.infrastructure.models import ExpenseWritebackJobRecord


class SQLAlchemyExpenseWritebackJobRepository:
    """报销写回任务仓储，负责持久化读写。"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """初始化 SQLAlchemyExpenseWritebackJobRepository。

        Args:
            session_factory: 数据库会话工厂。
        """
        self._session_factory = session_factory

    async def save(self, job: ExpenseWritebackJob) -> None:
        """保存报销写回任务。

        Args:
            job: 后台任务对象。
        """
        async with self._session_factory() as session:
            row = await session.get(ExpenseWritebackJobRecord, job.job_id)
            if row is None:
                session.add(ExpenseWritebackJobRecord.from_domain(job))
            else:
                row.apply_domain(job)
            await session.commit()

    async def get(self, tenant_id: str, job_id: str) -> ExpenseWritebackJob | None:
        """读取报销写回任务。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            job_id: 任务 ID。

        Returns:
            报销写回任务无结果。
        """
        async with self._session_factory() as session:
            row = await session.get(ExpenseWritebackJobRecord, job_id)
            if row is None or row.tenant_id != tenant_id:
                return None
            return row.to_domain()

    async def list(self, tenant_id: str, limit: int = 100) -> list[ExpenseWritebackJob]:
        """查询报销写回任务。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            limit: 返回记录的最大数量。

        Returns:
            结果列表。
        """
        statement = (
            select(ExpenseWritebackJobRecord)
            .where(ExpenseWritebackJobRecord.tenant_id == tenant_id)
            .order_by(
                ExpenseWritebackJobRecord.created_at.desc(),
                ExpenseWritebackJobRecord.job_id.desc(),
            )
            .limit(limit)
        )
        async with self._session_factory() as session:
            rows = list((await session.execute(statement)).scalars().all())
        return [row.to_domain() for row in rows]
