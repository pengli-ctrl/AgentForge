"""SQLAlchemy附件仓储模块。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentforge.platform.modules.expense.domain.attachment import ExpenseAttachment
from agentforge.platform.modules.expense.infrastructure.models import ExpenseAttachmentRecord


class SQLAlchemyExpenseAttachmentRepository:
    """报销附件仓储，负责持久化读写。"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """初始化 SQLAlchemyExpenseAttachmentRepository。

        Args:
            session_factory: 数据库会话工厂。
        """
        self._session_factory = session_factory

    async def save(self, attachment: ExpenseAttachment) -> None:
        """保存报销附件。

        Args:
            attachment: 附件。
        """
        async with self._session_factory() as session:
            record = await session.get(ExpenseAttachmentRecord, attachment.attachment_id)
            if record is None:
                session.add(ExpenseAttachmentRecord.from_domain(attachment))
            else:
                record.apply_domain(attachment)
            await session.commit()

    async def get(self, tenant_id: str, attachment_id: str) -> ExpenseAttachment | None:
        """读取报销附件。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            attachment_id: 附件 ID。

        Returns:
            报销附件无结果。
        """
        async with self._session_factory() as session:
            record = await session.get(ExpenseAttachmentRecord, attachment_id)
            if record is None or record.tenant_id != tenant_id:
                return None
            return record.to_domain()

    async def list_by_ids(
        self, tenant_id: str, attachment_ids: list[str]
    ) -> list[ExpenseAttachment]:
        """查询由。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            attachment_ids: 附件 ID 列表。

        Returns:
            结果列表。
        """
        if not attachment_ids:
            return []
        statement = select(ExpenseAttachmentRecord).where(
            ExpenseAttachmentRecord.tenant_id == tenant_id,
            ExpenseAttachmentRecord.attachment_id.in_(attachment_ids),
        )
        async with self._session_factory() as session:
            records = list((await session.execute(statement)).scalars().all())
        return [record.to_domain() for record in records]
