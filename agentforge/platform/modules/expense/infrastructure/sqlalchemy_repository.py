"""SQLAlchemy仓储模块。"""

from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentforge.platform.modules.expense.domain.claim import ExpenseClaim, ExpenseClaimStatus
from agentforge.platform.modules.expense.infrastructure.models import ExpenseClaimRecord


class SQLAlchemyExpenseClaimRepository:
    """报销单仓储，负责持久化读写。"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """初始化 SQLAlchemyExpenseClaimRepository。

        Args:
            session_factory: 数据库会话工厂。
        """
        self._session_factory = session_factory

    async def save(self, claim: ExpenseClaim) -> None:
        """保存报销单。

        Args:
            claim: 报销单对象。
        """
        async with self._session_factory() as session:
            record = await session.get(ExpenseClaimRecord, claim.claim_id)
            if record is None:
                session.add(ExpenseClaimRecord.from_domain(claim))
            else:
                record.apply_domain(claim)
            await session.commit()

    async def get(self, tenant_id: str, claim_id: str) -> ExpenseClaim | None:
        """获取报销单。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            claim_id: 报销单 ID。

        Returns:
            报销报销单无结果。
        """
        async with self._session_factory() as session:
            record = await session.get(ExpenseClaimRecord, claim_id)
            if record is None or record.tenant_id != tenant_id:
                return None
            return record.to_domain()

    async def get_by_idempotency_key(
        self,
        tenant_id: str,
        idempotency_key: str,
    ) -> ExpenseClaim | None:
        """获取由键。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            idempotency_key: 幂等键，用于避免重复处理。

        Returns:
            报销报销单无结果。
        """
        async with self._session_factory() as session:
            statement = select(ExpenseClaimRecord).where(
                ExpenseClaimRecord.tenant_id == tenant_id,
                ExpenseClaimRecord.idempotency_key == idempotency_key,
            )
            record = (await session.execute(statement)).scalar_one_or_none()
            return record.to_domain() if record is not None else None

    async def list_page(
        self,
        tenant_id: str,
        *,
        status: ExpenseClaimStatus | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> tuple[list[ExpenseClaim], str | None]:
        """查询页面。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            status: 目标状态。
            limit: 返回记录的最大数量。
            cursor: 分页游标。

        Returns:
            结果元组。
        """
        offset = self._cursor_offset(cursor)
        statement = select(ExpenseClaimRecord).where(ExpenseClaimRecord.tenant_id == tenant_id)
        if status is not None:
            statement = statement.where(ExpenseClaimRecord.status == status.value)
        statement = (
            statement.order_by(
                ExpenseClaimRecord.created_at.desc(),
                ExpenseClaimRecord.claim_id.desc(),
            )
            .offset(offset)
            .limit(limit + 1)
        )
        async with self._session_factory() as session:
            records = list((await session.execute(statement)).scalars().all())
        has_more = len(records) > limit
        page = records[:limit]
        next_cursor = str(offset + limit) if has_more else None
        return [record.to_domain() for record in page], next_cursor

    async def list_all(
        self,
        tenant_id: str,
        *,
        status: ExpenseClaimStatus | None = None,
        limit: int = 10_000,
    ) -> list[ExpenseClaim]:
        """查询全部。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            status: 目标状态。
            limit: 返回记录的最大数量。

        Returns:
            结果列表。
        """
        statement = select(ExpenseClaimRecord).where(ExpenseClaimRecord.tenant_id == tenant_id)
        if status is not None:
            statement = statement.where(ExpenseClaimRecord.status == status.value)
        statement = statement.order_by(
            ExpenseClaimRecord.created_at.desc(),
            ExpenseClaimRecord.claim_id.desc(),
        ).limit(limit)
        async with self._session_factory() as session:
            records = list((await session.execute(statement)).scalars().all())
        return [record.to_domain() for record in records]

    async def list_tenants(self) -> list[str]:
        """查询租户。

        Returns:
            结果列表。
        """
        statement = select(ExpenseClaimRecord.tenant_id).distinct()
        async with self._session_factory() as session:
            return list((await session.execute(statement)).scalars().all())

    @staticmethod
    def _cursor_offset(cursor: str | None) -> int:
        """解析游标对应的分页偏移量。

        Args:
            cursor: 分页游标。

        Returns:
            整数结果。

        Raises:
            ValueError: 输入值或业务状态不合法时抛出。
        """
        if cursor is None:
            return 0
        try:
            offset = int(cursor)
        except ValueError as exc:
            raise ValueError("invalid cursor") from exc
        if offset < 0:
            raise ValueError("invalid cursor")
        return offset

    async def sum_amount_cents(
        self,
        tenant_id: str,
        statuses: set[ExpenseClaimStatus],
        date_from: date,
        date_to: date,
    ) -> int:
        """汇总报销金额分值。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            statuses: 输入参数。
            date_from: 从。
            date_to: 到。

        Returns:
            整数结果。
        """
        if not statuses:
            return 0
        statement = select(func.coalesce(func.sum(ExpenseClaimRecord.amount_cents), 0)).where(
            ExpenseClaimRecord.tenant_id == tenant_id,
            ExpenseClaimRecord.status.in_([status.value for status in statuses]),
            ExpenseClaimRecord.expense_date >= date_from,
            ExpenseClaimRecord.expense_date <= date_to,
        )
        async with self._session_factory() as session:
            value = (await session.execute(statement)).scalar_one()
        return int(value or 0)
