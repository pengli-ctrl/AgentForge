"""记忆成本仓储模块。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from agentforge.platform.domain.cost import CostRecord


class MemoryCostRepository:
    """成本仓储，负责持久化读写。"""

    def __init__(self) -> None:
        """初始化 MemoryCostRepository。"""
        self.records: list[CostRecord] = []

    async def save(self, record: CostRecord) -> None:
        """保存成本。

        Args:
            record: 待处理的领域记录。
        """
        self.records.append(record)

    async def total_for_tenant(self, tenant_id: str) -> float:
        """获取租户的总计。

        Args:
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            数值结果。
        """
        return sum(record.amount for record in self.records if record.tenant_id == tenant_id)

    async def monthly_total_for_tenant(self, tenant_id: str, now: datetime) -> float:
        """获取租户的月度总计。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            now: 输入参数。

        Returns:
            数值结果。
        """
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return sum(
            record.amount
            for record in self.records
            if record.tenant_id == tenant_id and record.created_at >= month_start
        )

    async def daily_summary(self, tenant_id: str, days: int = 30) -> list[dict]:
        """生成每日摘要。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            days: 统计天数。

        Returns:
            结果列表。
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        bucket: dict[str, dict] = {}
        for record in self.records:
            if record.tenant_id != tenant_id:
                continue
            if record.created_at < cutoff:
                continue
            day = record.created_at.date().isoformat()
            entry = bucket.setdefault(
                day,
                {
                    "date": day,
                    "request_count": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "amount": 0.0,
                },
            )
            entry["request_count"] += 1
            entry["input_tokens"] += record.input_tokens
            entry["output_tokens"] += record.output_tokens
            entry["amount"] += record.amount
        return [bucket[key] for key in sorted(bucket)]

    async def list_tenants(self) -> list[str]:
        """查询租户。

        Returns:
            结果列表。
        """
        seen: dict[str, None] = {}
        for record in self.records:
            seen.setdefault(record.tenant_id, None)
        return list(seen.keys())

    async def summary_for_tenant(self, tenant_id: str) -> dict:
        """获取租户的摘要。

        Args:
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            结构化结果字典。
        """
        records = [record for record in self.records if record.tenant_id == tenant_id]
        by_model: dict[tuple[str, str], dict] = {}
        for record in records:
            key = (record.model_name, record.provider)
            summary = by_model.setdefault(
                key,
                {
                    "model_name": record.model_name,
                    "provider": record.provider,
                    "request_count": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "amount": 0.0,
                },
            )
            summary["request_count"] += 1
            summary["input_tokens"] += record.input_tokens
            summary["output_tokens"] += record.output_tokens
            summary["amount"] += record.amount
        return {
            "tenant_id": tenant_id,
            "request_count": len(records),
            "input_tokens": sum(record.input_tokens for record in records),
            "output_tokens": sum(record.output_tokens for record in records),
            "total_amount": sum(record.amount for record in records),
            "by_model": list(by_model.values()),
        }
