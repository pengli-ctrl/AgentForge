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
        """执行一次离线回归并持久化运行记录与质量报告。"""
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
        return await self._repository.get_run(run_id)

    async def list_runs(self, tenant_id: str, limit: int = 100) -> list[RegressionRun]:
        return await self._repository.list_runs(tenant_id, limit=limit)

    async def load_golden(self, tenant_id: str, limit: int = 100) -> list[GoldenItem]:
        return await self._repository.list_golden(tenant_id, limit=limit)


def generate_run_id() -> str:
    return f"run-{uuid.uuid4().hex[:12]}"
