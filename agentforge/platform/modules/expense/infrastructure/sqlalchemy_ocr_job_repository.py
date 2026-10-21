"""SQLAlchemyOCR任务仓储模块。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentforge.platform.modules.expense.domain.ocr_job import ExpenseOcrJob
from agentforge.platform.modules.expense.infrastructure.models import ExpenseOcrJobRecord


class SQLAlchemyExpenseOcrJobRepository:
    """报销OCR任务仓储，负责持久化读写。"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """初始化 SQLAlchemyExpenseOcrJobRepository。

        Args:
            session_factory: 数据库会话工厂。
        """
        self._session_factory = session_factory

    async def save(self, job: ExpenseOcrJob) -> None:
        """保存报销OCR任务。

        Args:
            job: 后台任务对象。
        """
        async with self._session_factory() as session:
            row = await session.get(ExpenseOcrJobRecord, job.job_id)
            if row is None:
                session.add(ExpenseOcrJobRecord.from_domain(job))
            else:
                row.apply_domain(job)
            await session.commit()

    async def get(self, tenant_id: str, job_id: str) -> ExpenseOcrJob | None:
        """读取报销OCR任务。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            job_id: 任务 ID。

        Returns:
            报销OCR任务无结果。
        """
        async with self._session_factory() as session:
            row = await session.get(ExpenseOcrJobRecord, job_id)
            if row is None or row.tenant_id != tenant_id:
                return None
            return row.to_domain()

    async def list(self, tenant_id: str, limit: int = 100) -> list[ExpenseOcrJob]:
        """查询报销OCR任务。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            limit: 返回记录的最大数量。

        Returns:
            结果列表。
        """
        statement = (
            select(ExpenseOcrJobRecord)
            .where(ExpenseOcrJobRecord.tenant_id == tenant_id)
            .order_by(
                ExpenseOcrJobRecord.created_at.desc(),
                ExpenseOcrJobRecord.job_id.desc(),
            )
            .limit(limit)
        )
        async with self._session_factory() as session:
            rows = list((await session.execute(statement)).scalars().all())
        return [row.to_domain() for row in rows]
