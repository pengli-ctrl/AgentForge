"""AgentForge 平台应用服务层：regression_runner。

本模块实现 regression_runner 质量评估逻辑，用于度量、回归和控制上线风险。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：RegressionRunner。
- 主要函数：generate_run_id。
"""

from __future__ import annotations

import uuid

from agentforge.platform.application.classification_evaluation_service import (
    ClassificationEvaluationService,
)
from agentforge.platform.application.ports import RegressionRepository
from agentforge.platform.application.quality_gate_service import (
    QualityGateService,
    QualityGateVerdict,
)
from agentforge.platform.application.retrieval_evaluation_service import (
    RetrievalEvaluationService,
)
from agentforge.platform.domain.quality import ClassificationGoldenItem, ReleaseCandidate
from agentforge.platform.domain.regression import (
    GoldenItem,
    QualityReport,
    RegressionRun,
    RegressionRunStatus,
)
from agentforge.platform.domain.retrieval import GoldenQuery


class RegressionRunner:
    """离线回归运行器。

    加载租户的 Golden Dataset 样本，对每一条 GoldenItem 同时执行召回评估与
    分类评估，聚合指标后交给质量门禁判定，并把一次回归的结果以
    RegressionRun + QualityReport 持久化，便于后续对比回归。

    回归可以完全离线进行：数据中心由注入的 RetrievalEvaluationService 与
    ClassificationEvaluationService 决定（测试时注入内存实现）。
    """

    def __init__(
        self,
        regression_repository: RegressionRepository,
        retrieval_evaluation_service: RetrievalEvaluationService,
        classification_evaluation_service: ClassificationEvaluationService,
        quality_gate_service: QualityGateService | None = None,
    ) -> None:
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Args:
            regression_repository: RegressionRepository，调用方传入的 regression_repository 参数。
            retrieval_evaluation_service: RetrievalEvaluationService，调用方传入的
                retrieval_evaluation_service 参数。
            classification_evaluation_service: ClassificationEvaluationService，调用方传入的
                classification_evaluation_service 参数。
            quality_gate_service: QualityGateService | None，调用方传入的 quality_gate_service 参数。

        Returns:
            None，函数执行后的结果。
        """
        self._repository = regression_repository
        self._retrieval_eval = retrieval_evaluation_service
        self._classification_eval = classification_evaluation_service
        self._gate = quality_gate_service or QualityGateService()

    async def run(
        self,
        tenant_id: str,
        candidate: ReleaseCandidate,
        k: int = 5,
        rerank: bool = True,
    ) -> QualityReport:
        """执行 run 对应的逻辑，并返回处理结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。
            candidate: ReleaseCandidate，调用方传入的 candidate 参数。
            k: int，调用方传入的 k 参数。
            rerank: bool，调用方传入的 rerank 参数。

        Returns:
            QualityReport，函数执行后的结果。
        """
        golden = await self._repository.list_golden(tenant_id)

        # 组装召回评估的 GoldenQuery 列表。
        golden_queries = self._to_golden_queries(golden)
        retrieval_report = None
        if golden_queries:
            retrieval_report = await self._retrieval_eval.evaluate(
                golden_queries,
                k=k,
                rerank=rerank,
                mode="hybrid",
            )

        # 组装分类评估样本列表（仅取声明了期望分类的 Golden 项）。
        classification_items = [item for item in golden if item.expected_intent]
        classification_report = None
        if classification_items:
            classification_samples = [
                ClassificationGoldenItem(
                    tenant_id=item.tenant_id,
                    query=item.query,
                    expected_intent=item.expected_intent or "",
                    expected_priority=item.expected_priority or "p3",
                    expected_risk_level=item.expected_risk_level or "low",
                )
                for item in classification_items
            ]
            classification_report = await self._classification_eval.evaluate(classification_samples)

        metrics: dict[str, float] = {}
        if retrieval_report is not None:
            metrics["recall_at_k"] = retrieval_report.recall_at_k
            metrics["citation_accuracy"] = retrieval_report.citation_accuracy
        if classification_report is not None:
            metrics["classification_accuracy"] = classification_report.classification_accuracy
            metrics["priority_accuracy"] = classification_report.priority_accuracy
            metrics["structured_output_rate"] = classification_report.structured_output_rate
            metrics["high_risk_miss_rate"] = classification_report.high_risk_miss_rate

        gate_result = self._gate.gate(
            candidate=candidate,
            retrieval=retrieval_report,
            classification=classification_report,
        )
        verdict = gate_result.verdict.value

        run = RegressionRun(
            run_id=generate_run_id(),
            tenant_id=tenant_id,
            candidate_id=candidate.candidate_id,
            status=(
                RegressionRunStatus.PASSED
                if gate_result.verdict == QualityGateVerdict.PASS
                else (
                    RegressionRunStatus.FAILED
                    if gate_result.verdict == QualityGateVerdict.BLOCK
                    else RegressionRunStatus.HOLD
                )
            ),
            recall_at_k=metrics.get("recall_at_k", 0.0),
            citation_accuracy=metrics.get("citation_accuracy", 0.0),
            classification_accuracy=metrics.get("classification_accuracy", 0.0),
            priority_accuracy=metrics.get("priority_accuracy", 0.0),
            structured_output_rate=metrics.get("structured_output_rate", 0.0),
            high_risk_miss_rate=metrics.get("high_risk_miss_rate", 0.0),
            verdict=verdict,
        )
        await self._repository.save_run(run)

        report = QualityReport(
            report_id=f"rep-{run.run_id}",
            run_id=run.run_id,
            candidate_id=candidate.candidate_id,
            tenant_id=tenant_id,
            verdict=verdict,
            metrics=metrics,
            passed=gate_result.passed,
            warned=gate_result.warned,
            failed=gate_result.failed,
        )
        await self._repository.save_report(report)
        return report

    @staticmethod
    def _to_golden_queries(items: list[GoldenItem]) -> list[GoldenQuery]:
        """执行 _to_golden_queries 对应的逻辑，并返回处理结果。

        Args:
            items: list[GoldenItem]，调用方传入的 items 参数。

        Returns:
            list[GoldenQuery]，函数执行后的结果。
        """
        return [
            GoldenQuery(
                tenant_id=item.tenant_id,
                query=item.query,
                expected_chunk_ids=list(item.expected_chunk_ids),
                expected_citations=list(item.expected_citations),
            )
            for item in items
        ]

    async def get_run(self, run_id: str) -> RegressionRun | None:
        """读取并返回指定数据，并返回调用方需要的结果。

        Args:
            run_id: str，调用方传入的 run_id 参数。

        Returns:
            RegressionRun | None，函数执行后的结果。
        """
        return await self._repository.get_run(run_id)

    async def list_runs(self, tenant_id: str, limit: int = 100) -> list[RegressionRun]:
        """查询并返回列表结果，并返回调用方需要的结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。
            limit: int，调用方传入的 limit 参数。

        Returns:
            list[RegressionRun]，函数执行后的结果。
        """
        return await self._repository.list_runs(tenant_id, limit=limit)

    async def load_golden(self, tenant_id: str, limit: int = 100) -> list[GoldenItem]:
        """加载配置或资源，并返回调用方需要的结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。
            limit: int，调用方传入的 limit 参数。

        Returns:
            list[GoldenItem]，函数执行后的结果。
        """
        return await self._repository.list_golden(tenant_id, limit=limit)


def generate_run_id() -> str:
    """执行 generate_run_id 对应的逻辑，并返回处理结果。

    Returns:
        str，函数执行后的结果。
    """
    return f"run-{uuid.uuid4().hex[:12]}"
