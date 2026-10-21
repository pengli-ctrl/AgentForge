"""SQLAlchemy发票仓储模块。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentforge.platform.modules.expense.domain.invoice import ExpenseInvoice, ExpenseInvoiceStatus
from agentforge.platform.modules.expense.infrastructure.models import ExpenseInvoiceRecord


class SQLAlchemyExpenseInvoiceRepository:
    """报销发票仓储，负责持久化读写。"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """初始化 SQLAlchemyExpenseInvoiceRepository。

        Args:
            session_factory: 数据库会话工厂。
        """
        self._session_factory = session_factory

    async def save(self, invoice: ExpenseInvoice) -> None:
        """保存报销发票。

        Args:
            invoice: 发票对象。
        """
        async with self._session_factory() as session:
            row = await session.get(ExpenseInvoiceRecord, invoice.invoice_id)
            if row is None:
                session.add(ExpenseInvoiceRecord.from_domain(invoice))
            else:
                row.apply_domain(invoice)
            await session.commit()

    async def get(self, tenant_id: str, invoice_id: str) -> ExpenseInvoice | None:
        """读取报销发票。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            invoice_id: 发票 ID。

        Returns:
            报销发票无结果。
        """
        async with self._session_factory() as session:
            row = await session.get(ExpenseInvoiceRecord, invoice_id)
            if row is None or row.tenant_id != tenant_id:
                return None
            return row.to_domain()

    async def get_active_by_fingerprint(
        self,
        tenant_id: str,
        fingerprint: str,
    ) -> ExpenseInvoice | None:
        """获取活跃由指纹。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            fingerprint: 指纹。

        Returns:
            报销发票无结果。
        """
        statement = select(ExpenseInvoiceRecord).where(
            ExpenseInvoiceRecord.tenant_id == tenant_id,
            ExpenseInvoiceRecord.fingerprint == fingerprint,
            ExpenseInvoiceRecord.status == ExpenseInvoiceStatus.ACTIVE.value,
            ExpenseInvoiceRecord.duplicate_key.is_not(None),
        )
        async with self._session_factory() as session:
            row = (await session.execute(statement)).scalars().first()
        return row.to_domain() if row is not None else None

    async def list_by_claim(self, tenant_id: str, claim_id: str) -> list[ExpenseInvoice]:
        """查询由报销单。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            claim_id: 报销单 ID。

        Returns:
            结果列表。
        """
        statement = (
            select(ExpenseInvoiceRecord)
            .where(
                ExpenseInvoiceRecord.tenant_id == tenant_id,
                ExpenseInvoiceRecord.claim_id == claim_id,
            )
            .order_by(ExpenseInvoiceRecord.created_at, ExpenseInvoiceRecord.invoice_id)
        )
        async with self._session_factory() as session:
            rows = list((await session.execute(statement)).scalars().all())
        return [row.to_domain() for row in rows]

    async def list(self, tenant_id: str, limit: int = 200) -> list[ExpenseInvoice]:
        """查询报销发票。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            limit: 返回记录的最大数量。

        Returns:
            结果列表。
        """
        statement = (
            select(ExpenseInvoiceRecord)
            .where(ExpenseInvoiceRecord.tenant_id == tenant_id)
            .order_by(
                ExpenseInvoiceRecord.created_at.desc(),
                ExpenseInvoiceRecord.invoice_id.desc(),
            )
            .limit(limit)
        )
        async with self._session_factory() as session:
            rows = list((await session.execute(statement)).scalars().all())
        return [row.to_domain() for row in rows]
