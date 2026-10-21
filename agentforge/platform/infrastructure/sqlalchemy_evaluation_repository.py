"""SQLAlchemy评估仓储模块。"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentforge.platform.domain.evaluation import EvaluationSample
from agentforge.platform.infrastructure.db.models import EvaluationSampleRecord


class SQLAlchemyEvaluationRepository:
    """评估仓储，负责持久化读写。"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """初始化 SQLAlchemyEvaluationRepository。

        Args:
            session_factory: 数据库会话工厂。
        """
        self._session_factory = session_factory

    async def save(self, sample: EvaluationSample) -> None:
        """保存评估。

        Args:
            sample: 评估样本。
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
        """查询样本。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            limit: 返回记录的最大数量。
            action: 待执行动作名称。

        Returns:
            结果列表。
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
        """处理摘要。

        Args:
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            结构化结果字典。
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
