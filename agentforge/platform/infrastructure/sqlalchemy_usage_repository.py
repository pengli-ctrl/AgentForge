"""SQLAlchemy用量仓储模块。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentforge.platform.domain.usage import UsageMetric, UsageRecord
from agentforge.platform.infrastructure.db.usage_record_model import UsageRecordModel


class SQLAlchemyUsageRepository:
    """用量仓储，负责持久化读写。"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """初始化 SQLAlchemyUsageRepository。

        Args:
            session_factory: 数据库会话工厂。
        """
        self._session_factory = session_factory

    async def add(self, record: UsageRecord) -> bool:
        """保存用量。

        Args:
            record: 待处理的领域记录。

        Returns:
            操作是否成功。
        """
        row = UsageRecordModel(
            record_id=record.record_id,
            tenant_id=record.tenant_id,
            metric=record.metric.value,
            quantity=record.quantity,
            source=record.source,
            idempotency_key=record.idempotency_key,
            occurred_at=record.occurred_at,
            payload=record.metadata,
        )
        async with self._session_factory() as session:
            session.add(row)
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                return False
        return True

    async def total(
        self,
        tenant_id: str,
        metric: UsageMetric,
        *,
        start: datetime,
        end: datetime,
    ) -> int:
        """统计用量。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            metric: 用量指标。
            start: 统计或查询周期的开始时间。
            end: 统计或查询周期的结束时间。

        Returns:
            整数结果。
        """
        statement = select(func.coalesce(func.sum(UsageRecordModel.quantity), 0)).where(
            UsageRecordModel.tenant_id == tenant_id,
            UsageRecordModel.metric == metric.value,
            UsageRecordModel.occurred_at >= start,
            UsageRecordModel.occurred_at < end,
        )
        async with self._session_factory() as session:
            return int((await session.execute(statement)).scalar_one())

    async def list(
        self,
        tenant_id: str,
        *,
        start: datetime,
        end: datetime,
        limit: int = 1000,
    ) -> list[UsageRecord]:
        """查询用量。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            start: 统计或查询周期的开始时间。
            end: 统计或查询周期的结束时间。
            limit: 返回记录的最大数量。

        Returns:
            结果列表。
        """
        statement = (
            select(UsageRecordModel)
            .where(
                UsageRecordModel.tenant_id == tenant_id,
                UsageRecordModel.occurred_at >= start,
                UsageRecordModel.occurred_at < end,
            )
            .order_by(UsageRecordModel.occurred_at.desc())
            .limit(limit)
        )
        async with self._session_factory() as session:
            rows = list((await session.execute(statement)).scalars().all())
        return [self._to_domain(row) for row in rows]

    async def totals(
        self,
        tenant_id: str,
        *,
        start: datetime,
        end: datetime,
    ) -> dict[UsageMetric, int]:
        """按指标汇总用量。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            start: 统计或查询周期的开始时间。
            end: 统计或查询周期的结束时间。

        Returns:
            结构化结果字典。
        """
        statement = (
            select(UsageRecordModel.metric, func.sum(UsageRecordModel.quantity))
            .where(
                UsageRecordModel.tenant_id == tenant_id,
                UsageRecordModel.occurred_at >= start,
                UsageRecordModel.occurred_at < end,
            )
            .group_by(UsageRecordModel.metric)
        )
        async with self._session_factory() as session:
            rows = (await session.execute(statement)).all()
        result = {metric: 0 for metric in UsageMetric}
        for metric_name, quantity in rows:
            result[UsageMetric(metric_name)] = int(quantity or 0)
        return result

    @staticmethod
    def _to_domain(row: UsageRecordModel) -> UsageRecord:
        """转换领域。

        Args:
            row: 记录。

        Returns:
            用量记录结果。
        """
        return UsageRecord(
            record_id=row.record_id,
            tenant_id=row.tenant_id,
            metric=UsageMetric(row.metric),
            quantity=row.quantity,
            source=row.source,
            idempotency_key=row.idempotency_key,
            occurred_at=row.occurred_at,
            metadata=dict(row.payload or {}),
        )


__all__ = ["SQLAlchemyUsageRepository"]
