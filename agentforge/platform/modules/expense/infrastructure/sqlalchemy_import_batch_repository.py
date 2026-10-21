"""SQLAlchemy导入批次仓储模块。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentforge.platform.modules.expense.domain.import_batch import ExpenseImportBatch
from agentforge.platform.modules.expense.infrastructure.models import ExpenseImportBatchRecord


class SQLAlchemyExpenseImportBatchRepository:
    """报销导入批次仓储，负责持久化读写。"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """初始化 SQLAlchemyExpenseImportBatchRepository。

        Args:
            session_factory: 数据库会话工厂。
        """
        self._session_factory = session_factory

    async def save(self, batch: ExpenseImportBatch) -> None:
        """保存报销导入批次。

        Args:
            batch: 批次。
        """
        async with self._session_factory() as session:
            row = await session.get(ExpenseImportBatchRecord, batch.batch_id)
            if row is None:
                session.add(ExpenseImportBatchRecord.from_domain(batch))
            else:
                row.apply_domain(batch)
            await session.commit()

    async def get(self, tenant_id: str, batch_id: str) -> ExpenseImportBatch | None:
        """获取报销导入批次。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            batch_id: 批次 ID。

        Returns:
            报销导入批次无结果。
        """
        async with self._session_factory() as session:
            row = await session.get(ExpenseImportBatchRecord, batch_id)
            if row is None or row.tenant_id != tenant_id:
                return None
            return row.to_domain()

    async def list(self, tenant_id: str, limit: int = 100) -> list[ExpenseImportBatch]:
        """查询报销导入批次。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            limit: 返回记录的最大数量。

        Returns:
            结果列表。
        """
        statement = (
            select(ExpenseImportBatchRecord)
            .where(ExpenseImportBatchRecord.tenant_id == tenant_id)
            .order_by(
                ExpenseImportBatchRecord.created_at.desc(),
                ExpenseImportBatchRecord.batch_id.desc(),
            )
            .limit(limit)
        )
        async with self._session_factory() as session:
            rows = list((await session.execute(statement)).scalars().all())
        return [row.to_domain() for row in rows]
