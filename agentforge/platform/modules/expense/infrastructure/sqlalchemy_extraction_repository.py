"""SQLAlchemy提取仓储模块。"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentforge.platform.modules.expense.domain.extraction import ExpenseExtractionRecord
from agentforge.platform.modules.expense.infrastructure.models import ExpenseExtractionRecordModel


class SQLAlchemyExpenseExtractionRepository:
    """报销提取仓储，负责持久化读写。"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """初始化 SQLAlchemyExpenseExtractionRepository。

        Args:
            session_factory: 数据库会话工厂。
        """
        self._session_factory = session_factory

    async def save(self, record: ExpenseExtractionRecord) -> None:
        """保存报销提取。

        Args:
            record: 待处理的领域记录。
        """
        async with self._session_factory() as session:
            row = await session.get(ExpenseExtractionRecordModel, record.extraction_id)
            if row is None:
                session.add(ExpenseExtractionRecordModel.from_domain(record))
            else:
                row.apply_domain(record)
            await session.commit()

    async def get(self, tenant_id: str, extraction_id: str) -> ExpenseExtractionRecord | None:
        """读取报销提取。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            extraction_id: 提取 ID。

        Returns:
            报销提取记录无结果。
        """
        async with self._session_factory() as session:
            row = await session.get(ExpenseExtractionRecordModel, extraction_id)
            if row is None or row.tenant_id != tenant_id:
                return None
            return row.to_domain()
