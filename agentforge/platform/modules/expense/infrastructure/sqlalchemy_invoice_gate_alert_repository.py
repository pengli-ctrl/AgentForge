"""SQLAlchemy发票门禁告警仓储模块。"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentforge.platform.modules.expense.domain.invoice import (
    InvoiceGateAlertState,
    InvoiceGateAlertStateStatus,
)
from agentforge.platform.modules.expense.infrastructure.models import ExpenseInvoiceGateAlertRecord


class SQLAlchemyExpenseInvoiceGateAlertRepository:
    """报销发票门禁告警仓储，负责持久化读写。"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """初始化 SQLAlchemyExpenseInvoiceGateAlertRepository。

        Args:
            session_factory: 数据库会话工厂。
        """
        self._session_factory = session_factory

    async def save(self, alert: InvoiceGateAlertState) -> None:
        """保存报销发票门禁告警。

        Args:
            alert: 告警。

        Raises:
            Exception: 操作无法完成时抛出。
        """
        async with self._session_factory() as session:
            row = await session.get(ExpenseInvoiceGateAlertRecord, alert.alert_id)
            if row is None and alert.status == InvoiceGateAlertStateStatus.ACTIVE:
                active = await self._find_active(session, alert.tenant_id, alert.alert_key)
                if active is not None:
                    return
                session.add(ExpenseInvoiceGateAlertRecord.from_domain(alert))
            elif row is None:
                session.add(ExpenseInvoiceGateAlertRecord.from_domain(alert))
            else:
                row.apply_domain(alert)
            try:
                await session.commit()
            except IntegrityError:
                # 并发巡检可能已创建相同的活跃键。
                await session.rollback()
                active = await self._find_active(session, alert.tenant_id, alert.alert_key)
                if active is None:
                    raise

    async def get(self, tenant_id: str, alert_id: str) -> InvoiceGateAlertState | None:
        """读取报销发票门禁告警。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            alert_id: 告警 ID。

        Returns:
            发票门禁告警状态无结果。
        """
        async with self._session_factory() as session:
            row = await session.get(ExpenseInvoiceGateAlertRecord, alert_id)
            if row is None or row.tenant_id != tenant_id:
                return None
            return row.to_domain()

    async def find_active(
        self,
        tenant_id: str,
        alert_key: str,
    ) -> InvoiceGateAlertState | None:
        """查找活跃。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            alert_key: 告警键。

        Returns:
            发票门禁告警状态无结果。
        """
        async with self._session_factory() as session:
            row = await self._find_active(session, tenant_id, alert_key)
            return row.to_domain() if row is not None else None

    async def count_occurrences(self, tenant_id: str, alert_key: str) -> int:
        """统计报销发票门禁告警。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            alert_key: 告警键。

        Returns:
            整数结果。
        """
        statement = (
            select(func.count())
            .select_from(ExpenseInvoiceGateAlertRecord)
            .where(
                ExpenseInvoiceGateAlertRecord.tenant_id == tenant_id,
                ExpenseInvoiceGateAlertRecord.alert_key == alert_key,
            )
        )
        async with self._session_factory() as session:
            return int((await session.execute(statement)).scalar_one() or 0)

    async def list_all(
        self,
        tenant_id: str,
        limit: int = 10_000,
    ) -> list[InvoiceGateAlertState]:
        """查询全部。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            limit: 返回记录的最大数量。

        Returns:
            结果列表。
        """
        statement = (
            select(ExpenseInvoiceGateAlertRecord)
            .where(ExpenseInvoiceGateAlertRecord.tenant_id == tenant_id)
            .order_by(
                ExpenseInvoiceGateAlertRecord.created_at.desc(),
                ExpenseInvoiceGateAlertRecord.alert_id.desc(),
            )
            .limit(limit)
        )
        async with self._session_factory() as session:
            rows = list((await session.execute(statement)).scalars().all())
        return [row.to_domain() for row in rows]

    async def list_tenants(self) -> list[str]:
        """查询租户。

        Returns:
            结果列表。
        """
        statement = select(ExpenseInvoiceGateAlertRecord.tenant_id).distinct()
        async with self._session_factory() as session:
            return list((await session.execute(statement)).scalars().all())

    async def list_active(self, tenant_id: str) -> list[InvoiceGateAlertState]:
        """查询活跃。

        Args:
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            结果列表。
        """
        statement = (
            select(ExpenseInvoiceGateAlertRecord)
            .where(
                ExpenseInvoiceGateAlertRecord.tenant_id == tenant_id,
                ExpenseInvoiceGateAlertRecord.status == InvoiceGateAlertStateStatus.ACTIVE.value,
            )
            .order_by(
                ExpenseInvoiceGateAlertRecord.created_at,
                ExpenseInvoiceGateAlertRecord.alert_id,
            )
        )
        async with self._session_factory() as session:
            rows = list((await session.execute(statement)).scalars().all())
        return [row.to_domain() for row in rows]

    @staticmethod
    async def _find_active(
        session: AsyncSession,
        tenant_id: str,
        alert_key: str,
    ) -> ExpenseInvoiceGateAlertRecord | None:
        """查找活跃。

        Args:
            session: 当前会话。
            tenant_id: 租户 ID，用于数据隔离。
            alert_key: 告警键。

        Returns:
            报销发票门禁告警记录无结果。
        """
        statement = select(ExpenseInvoiceGateAlertRecord).where(
            ExpenseInvoiceGateAlertRecord.tenant_id == tenant_id,
            ExpenseInvoiceGateAlertRecord.alert_key == alert_key,
            ExpenseInvoiceGateAlertRecord.status == InvoiceGateAlertStateStatus.ACTIVE.value,
        )
        return (await session.execute(statement)).scalars().first()
