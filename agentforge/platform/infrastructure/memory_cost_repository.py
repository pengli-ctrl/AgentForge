"""AgentForge 平台基础设施层：memory_cost_repository。

本模块提供 memory_cost_repository 的内存实现，用于单元测试、本地开发和离线验证。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：MemoryCostRepository。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from agentforge.platform.domain.cost import CostRecord


class MemoryCostRepository:
    """MemoryCostRepository。

    MemoryCostRepository 负责数据读写，并确保租户隔离、事务一致性和持久化细节不泄漏到应用层。

    主要成员：
    - 方法 save()。
    - 方法 total_for_tenant()。
    - 方法 monthly_total_for_tenant()。
    - 方法 daily_summary()。
    - 方法 list_tenants()。
    - 方法 summary_for_tenant()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    def __init__(self) -> None:
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Returns:
            None，函数执行后的结果。
        """
        self.records: list[CostRecord] = []

    async def save(self, record: CostRecord) -> None:
        """执行 save 对应的核心操作，并保持调用契约稳定。

        Args:
            record: CostRecord，调用方传入的 record 参数。

        Returns:
            None，函数执行后的结果。
        """
        self.records.append(record)

    async def total_for_tenant(self, tenant_id: str) -> float:
        """执行 total_for_tenant 对应的逻辑，并返回处理结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。

        Returns:
            float，函数执行后的结果。
        """
        return sum(record.amount for record in self.records if record.tenant_id == tenant_id)

    async def monthly_total_for_tenant(self, tenant_id: str, now: datetime) -> float:
        """执行 monthly_total_for_tenant 对应的逻辑，并返回处理结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。
            now: datetime，调用方传入的 now 参数。

        Returns:
            float，函数执行后的结果。
        """
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return sum(
            record.amount
            for record in self.records
            if record.tenant_id == tenant_id and record.created_at >= month_start
        )

    async def daily_summary(self, tenant_id: str, days: int = 30) -> list[dict]:
        """执行 daily_summary 对应的逻辑，并返回处理结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。
            days: int，调用方传入的 days 参数。

        Returns:
            list[dict]，函数执行后的结果。
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
        """查询并返回列表结果，并返回调用方需要的结果。

        Returns:
            list[str]，函数执行后的结果。
        """
        seen: dict[str, None] = {}
        for record in self.records:
            seen.setdefault(record.tenant_id, None)
        return list(seen.keys())

    async def summary_for_tenant(self, tenant_id: str) -> dict:
        """执行 summary_for_tenant 对应的逻辑，并返回处理结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。

        Returns:
            dict，函数执行后的结果。
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
