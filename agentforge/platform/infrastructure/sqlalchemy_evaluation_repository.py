"""AgentForge 平台基础设施层：sqlalchemy_evaluation_repository。

本模块提供 sqlalchemy_evaluation_repository 的数据库持久化实现，负责事务、查询、租户隔离和一致性约束。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：SQLAlchemyEvaluationRepository。
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentforge.platform.domain.evaluation import EvaluationSample
from agentforge.platform.infrastructure.db.models import EvaluationSampleRecord


class SQLAlchemyEvaluationRepository:
    """SQLAlchemyEvaluationRepository。

    SQLAlchemyEvaluationRepository 负责数据读写，并确保租户隔离、事务一致性和持久化细节不泄漏到应用层。

    主要成员：
    - 方法 save()。
    - 方法 list_samples()。
    - 方法 summary()。

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

    async def save(self, sample: EvaluationSample) -> None:
        """执行 save 对应的核心操作，并保持调用契约稳定。

        Args:
            sample: EvaluationSample，调用方传入的 sample 参数。

        Returns:
            None，函数执行后的结果。
        """
        async with self._session_factory() as session:
            session.add(EvaluationSampleRecord.from_domain(sample))
            await session.commit()

    async def list_samples(
        self,
        tenant_id: str,
        limit: int = 100,
        action: str | None = None,
    ) -> list[EvaluationSample]:
        """查询并返回列表结果，并返回调用方需要的结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。
            limit: int，调用方传入的 limit 参数。
            action: str | None，调用方传入的 action 参数。

        Returns:
            list[EvaluationSample]，函数执行后的结果。
        """
        statement = select(EvaluationSampleRecord).where(
            EvaluationSampleRecord.tenant_id == tenant_id
        )
        if action is not None:
            statement = statement.where(EvaluationSampleRecord.action == action)
        statement = statement.order_by(EvaluationSampleRecord.created_at.desc()).limit(limit)
        async with self._session_factory() as session:
            records = (await session.execute(statement)).scalars().all()
        return [record.to_domain() for record in records]

    async def summary(self, tenant_id: str) -> dict:
        """执行 summary 对应的逻辑，并返回处理结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。

        Returns:
            dict，函数执行后的结果。
        """
        statement = (
            select(EvaluationSampleRecord.action, func.count(EvaluationSampleRecord.sample_id))
            .where(EvaluationSampleRecord.tenant_id == tenant_id)
            .group_by(EvaluationSampleRecord.action)
        )
        async with self._session_factory() as session:
            rows = (await session.execute(statement)).all()
        counts = {"accept": 0, "edit": 0, "reject": 0}
        for action, count in rows:
            if action in counts:
                counts[action] = int(count)
        sample_count = sum(counts.values())
        denominator = sample_count or 1
        return {
            "tenant_id": tenant_id,
            "sample_count": sample_count,
            "action_counts": counts,
            "acceptance_rate": counts["accept"] / denominator,
            "edit_rate": counts["edit"] / denominator,
            "rejection_rate": counts["reject"] / denominator,
            "draft_useful_rate": (counts["accept"] + counts["edit"]) / denominator,
        }
