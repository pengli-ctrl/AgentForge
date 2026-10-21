"""记忆用量仓储模块。"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime

from agentforge.platform.domain.usage import UsageMetric, UsageRecord


class MemoryUsageRepository:
    """用量仓储，负责持久化读写。"""

    def __init__(self) -> None:
        """初始化 MemoryUsageRepository。"""
        self._records: list[UsageRecord] = []
        self._idempotency: set[tuple[str, str]] = set()

    async def add(self, record: UsageRecord) -> bool:
        """保存用量。

        Args:
            record: 待处理的领域记录。

        Returns:
            操作是否成功。
        """
        key = (record.tenant_id, record.idempotency_key)
        if key in self._idempotency:
            return False
        self._idempotency.add(key)
        self._records.append(deepcopy(record))
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
        return sum(
            record.quantity
            for record in self._records
            if record.tenant_id == tenant_id
            and record.metric == metric
            and start <= record.occurred_at < end
        )

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
        records = [
            record
            for record in self._records
            if record.tenant_id == tenant_id and start <= record.occurred_at < end
        ]
        records.sort(key=lambda item: item.occurred_at, reverse=True)
        return [deepcopy(record) for record in records[:limit]]

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
        result = {metric: 0 for metric in UsageMetric}
        for record in self._records:
            if record.tenant_id == tenant_id and start <= record.occurred_at < end:
                result[record.metric] += record.quantity
        return result


__all__ = ["MemoryUsageRepository"]
