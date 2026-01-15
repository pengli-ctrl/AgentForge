"""AgentForge 平台基础设施层：sqlalchemy_regression_repository。

本模块提供 sqlalchemy_regression_repository 的数据库持久化实现，负责事务、查询、租户隔离和一致性约束。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：SQLAlchemyRegressionRepository。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentforge.platform.domain.regression import GoldenItem, QualityReport, RegressionRun
from agentforge.platform.infrastructure.db.models import GoldenItemRecord, RegressionRunRecord


class SQLAlchemyRegressionRepository:
    """SQLAlchemyRegressionRepository。

    SQLAlchemyRegressionRepository 负责数据读写，并确保租户隔离、事务一致性和持久化细节不泄漏到应用层。

    主要成员：
    - 方法 save_golden()。
    - 方法 list_golden()。
    - 方法 save_run()。
    - 方法 save_report()。
    - 方法 get_run()。
    - 方法 list_runs()。

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

    async def save_golden(self, item: GoldenItem) -> None:
        """保存业务数据，并返回调用方需要的结果。

        Args:
            item: GoldenItem，调用方传入的 item 参数。

        Returns:
            None，函数执行后的结果。
        """
        async with self._session_factory() as session:
            session.add(GoldenItemRecord.from_domain(item))
            await session.commit()

    async def list_golden(self, tenant_id: str, limit: int = 100) -> list[GoldenItem]:
        """查询并返回列表结果，并返回调用方需要的结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。
            limit: int，调用方传入的 limit 参数。

        Returns:
            list[GoldenItem]，函数执行后的结果。
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
        """保存业务数据，并返回调用方需要的结果。

        Args:
            run: RegressionRun，调用方传入的 run 参数。

        Returns:
            None，函数执行后的结果。
        """
        record = RegressionRunRecord.from_domain(run)
        async with self._session_factory() as session:
            session.add(record)
            await session.commit()

    async def save_report(self, report: QualityReport) -> None:
        """保存业务数据，并返回调用方需要的结果。

        Args:
            report: QualityReport，调用方传入的 report 参数。

        Returns:
            None，函数执行后的结果。
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
        """读取并返回指定数据，并返回调用方需要的结果。

        Args:
            run_id: str，调用方传入的 run_id 参数。

        Returns:
            RegressionRun | None，函数执行后的结果。
        """
        statement = select(RegressionRunRecord).where(RegressionRunRecord.run_id == run_id)
        async with self._session_factory() as session:
            record = (await session.execute(statement)).scalar_one_or_none()
        return record.to_domain() if record else None

    async def list_runs(self, tenant_id: str, limit: int = 100) -> list[RegressionRun]:
        """查询并返回列表结果，并返回调用方需要的结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。
            limit: int，调用方传入的 limit 参数。

        Returns:
            list[RegressionRun]，函数执行后的结果。
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
