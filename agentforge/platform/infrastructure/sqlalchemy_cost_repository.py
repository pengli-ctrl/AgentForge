"""AgentForge 平台基础设施层：sqlalchemy_cost_repository。

本模块提供 sqlalchemy_cost_repository 的数据库持久化实现，负责事务、查询、租户隔离和一致性约束。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：SQLAlchemyCostRepository。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentforge.platform.domain.cost import CostRecord
from agentforge.platform.infrastructure.db.models import CostRecordRecord


class SQLAlchemyCostRepository:
    """SQLAlchemyCostRepository。

    SQLAlchemyCostRepository 负责数据读写，并确保租户隔离、事务一致性和持久化细节不泄漏到应用层。

    主要成员：
    - 方法 save()。
    - 方法 total_for_tenant()。
    - 方法 monthly_total_for_tenant()。
    - 方法 list_tenants()。
    - 方法 daily_summary()。
    - 方法 summary_for_tenant()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Args:
            session_factory: async_sessionmaker[AsyncSession]，调用方传入的 session_factory 参数。

        Returns:
            None，函数执行后的结果。
        """
        self._session_factory = session_factory

    async def save(self, record: CostRecord) -> None:
        """执行 save 对应的核心操作，并保持调用契约稳定。

        Args:
            record: CostRecord，调用方传入的 record 参数。

        Returns:
            None，函数执行后的结果。
        """
        async with self._session_factory() as session:
            session.add(
                CostRecordRecord(
                    tenant_id=record.tenant_id,
                    task_id=record.task_id,
                    model_name=record.model_name,
                    provider=record.provider,
                    input_tokens=record.input_tokens,
                    output_tokens=record.output_tokens,
                    amount=record.amount,
                    created_at=record.created_at,
                )
            )
            await session.commit()

    async def total_for_tenant(self, tenant_id: str) -> float:
        """执行 total_for_tenant 对应的逻辑，并返回处理结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。

        Returns:
            float，函数执行后的结果。
        """
        async with self._session_factory() as session:
            statement = select(func.coalesce(func.sum(CostRecordRecord.amount), 0.0)).where(
                CostRecordRecord.tenant_id == tenant_id
            )
            return float((await session.execute(statement)).scalar_one())

    async def monthly_total_for_tenant(self, tenant_id: str, now: datetime) -> float:
        """执行 monthly_total_for_tenant 对应的逻辑，并返回处理结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。
            now: datetime，调用方传入的 now 参数。

        Returns:
            float，函数执行后的结果。
        """
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        async with self._session_factory() as session:
            statement = select(func.coalesce(func.sum(CostRecordRecord.amount), 0.0)).where(
                CostRecordRecord.tenant_id == tenant_id,
                CostRecordRecord.created_at >= month_start,
            )
            return float((await session.execute(statement)).scalar_one())

    async def list_tenants(self) -> list[str]:
        """查询并返回列表结果，并返回调用方需要的结果。

        Returns:
            list[str]，函数执行后的结果。
        """
        async with self._session_factory() as session:
            statement = select(CostRecordRecord.tenant_id).distinct()
            return list((await session.execute(statement)).scalars().all())

    async def daily_summary(self, tenant_id: str, days: int = 30) -> list[dict]:
        """执行 daily_summary 对应的逻辑，并返回处理结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。
            days: int，调用方传入的 days 参数。

        Returns:
            list[dict]，函数执行后的结果。
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        statement = (
            select(CostRecordRecord)
            .where(
                CostRecordRecord.tenant_id == tenant_id,
                CostRecordRecord.created_at >= cutoff,
            )
            .order_by(CostRecordRecord.created_at.asc())
        )
        async with self._session_factory() as session:
            records = (await session.execute(statement)).scalars().all()
        bucket: dict[str, dict] = {}
        for record in records:
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

    async def summary_for_tenant(self, tenant_id: str) -> dict:
        """执行 summary_for_tenant 对应的逻辑，并返回处理结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。

        Returns:
            dict，函数执行后的结果。
        """
        statement = (
            select(
                CostRecordRecord.model_name,
                CostRecordRecord.provider,
                func.count(CostRecordRecord.id),
                func.coalesce(func.sum(CostRecordRecord.input_tokens), 0),
                func.coalesce(func.sum(CostRecordRecord.output_tokens), 0),
                func.coalesce(func.sum(CostRecordRecord.amount), 0.0),
            )
            .where(CostRecordRecord.tenant_id == tenant_id)
            .group_by(CostRecordRecord.model_name, CostRecordRecord.provider)
        )
        async with self._session_factory() as session:
            rows = (await session.execute(statement)).all()
        by_model = [
            {
                "model_name": row[0],
                "provider": row[1],
                "request_count": int(row[2]),
                "input_tokens": int(row[3]),
                "output_tokens": int(row[4]),
                "amount": float(row[5]),
            }
            for row in rows
        ]
        return {
            "tenant_id": tenant_id,
            "request_count": sum(item["request_count"] for item in by_model),
            "input_tokens": sum(item["input_tokens"] for item in by_model),
            "output_tokens": sum(item["output_tokens"] for item in by_model),
            "total_amount": sum(item["amount"] for item in by_model),
            "by_model": by_model,
        }
