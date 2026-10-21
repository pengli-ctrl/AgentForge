"""SQLAlchemy回归仓储模块。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentforge.platform.domain.regression import GoldenItem, QualityReport, RegressionRun
from agentforge.platform.infrastructure.db.models import GoldenItemRecord, RegressionRunRecord


class SQLAlchemyRegressionRepository:
    """回归仓储，负责持久化读写。"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """初始化 SQLAlchemyRegressionRepository。

        Args:
            session_factory: 数据库会话工厂。
        """
        self._session_factory = session_factory

    async def save_golden(self, item: GoldenItem) -> None:
        """保存基准。

        Args:
            item: 条目。
        """
        async with self._session_factory() as session:
            session.add(GoldenItemRecord.from_domain(item))
            await session.commit()

    async def list_golden(self, tenant_id: str, limit: int = 100) -> list[GoldenItem]:
        """查询基准。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            limit: 返回记录的最大数量。

        Returns:
            结果列表。
        """
        statement = (
            select(GoldenItemRecord)
            .where(GoldenItemRecord.tenant_id == tenant_id)
            .order_by(GoldenItemRecord.created_at.desc())
            .limit(limit)
        )
        async with self._session_factory() as session:
            records = (await session.execute(statement)).scalars().all()
        return [record.to_domain() for record in records]

    async def save_run(self, run: RegressionRun) -> None:
        """保存运行。

        Args:
            run: 运行。
        """
        record = RegressionRunRecord.from_domain(run)
        async with self._session_factory() as session:
            session.add(record)
            await session.commit()

    async def save_report(self, report: QualityReport) -> None:
        """保存报告。

        Args:
            report: 报告。
        """
        run = await self.get_run(report.run_id)
        if run is None:
            return
        metrics = report.metrics
        # 用质量报告的指标回写运行摘要，保证运行时快照与报告一致。
        updated = run.model_copy(
            update={
                "verdict": report.verdict,
                "recall_at_k": metrics.get("recall_at_k", run.recall_at_k),
                "citation_accuracy": metrics.get("citation_accuracy", run.citation_accuracy),
                "classification_accuracy": metrics.get(
                    "classification_accuracy", run.classification_accuracy
                ),
                "priority_accuracy": metrics.get("priority_accuracy", run.priority_accuracy),
                "structured_output_rate": metrics.get(
                    "structured_output_rate", run.structured_output_rate
                ),
                "high_risk_miss_rate": metrics.get("high_risk_miss_rate", run.high_risk_miss_rate),
            }
        )
        record = RegressionRunRecord.from_domain(updated, report.model_dump(mode="json"))
        async with self._session_factory() as session:
            await session.merge(record)
            await session.commit()

    async def get_run(self, run_id: str) -> RegressionRun | None:
        """获取运行。

        Args:
            run_id: 运行记录 ID。

        Returns:
            回归运行无结果。
        """
        statement = select(RegressionRunRecord).where(RegressionRunRecord.run_id == run_id)
        async with self._session_factory() as session:
            record = (await session.execute(statement)).scalar_one_or_none()
        return record.to_domain() if record else None

    async def list_runs(self, tenant_id: str, limit: int = 100) -> list[RegressionRun]:
        """查询运行记录。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            limit: 返回记录的最大数量。

        Returns:
            结果列表。
        """
        statement = (
            select(RegressionRunRecord)
            .where(RegressionRunRecord.tenant_id == tenant_id)
            .order_by(RegressionRunRecord.created_at.desc())
            .limit(limit)
        )
        async with self._session_factory() as session:
            records = (await session.execute(statement)).scalars().all()
        return [record.to_domain() for record in records]
