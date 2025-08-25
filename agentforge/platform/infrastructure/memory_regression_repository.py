from __future__ import annotations

from agentforge.platform.domain.regression import GoldenItem, QualityReport, RegressionRun


class MemoryRegressionRepository:
    """内存版 Golden Dataset 回归仓库，供单元测试离线使用（无需 PostgreSQL）。"""

    def __init__(self) -> None:
        self._golden: dict[str, GoldenItem] = {}
        self._runs: dict[str, RegressionRun] = {}

    async def save_golden(self, item: GoldenItem) -> None:
        self._golden[item.item_id] = item

    async def list_golden(self, tenant_id: str, limit: int = 100) -> list[GoldenItem]:
        items = [i for i in self._golden.values() if i.tenant_id == tenant_id]
        items.sort(key=lambda x: x.created_at)
        return items[:limit]

    async def save_run(self, run: RegressionRun) -> None:
        self._runs[run.run_id] = run

    async def save_report(self, report: QualityReport) -> None:
        # 报告并入对应 run 的元信息由调用方管理，此处直接耦合 metric 摘要便于内存断言。
        run = self._runs.get(report.run_id)
        if run is not None:
            run = run.model_copy(
                update={
                    "verdict": report.verdict,
                    "recall_at_k": report.metrics.get("recall_at_k", run.recall_at_k),
                    "citation_accuracy": report.metrics.get(
                        "citation_accuracy", run.citation_accuracy
                    ),
                    "classification_accuracy": report.metrics.get(
                        "classification_accuracy", run.classification_accuracy
                    ),
                    "priority_accuracy": report.metrics.get(
                        "priority_accuracy", run.priority_accuracy
                    ),
                    "structured_output_rate": report.metrics.get(
                        "structured_output_rate", run.structured_output_rate
                    ),
                    "high_risk_miss_rate": report.metrics.get(
                        "high_risk_miss_rate", run.high_risk_miss_rate
                    ),
                }
            )
            self._runs[report.run_id] = run

    async def get_run(self, run_id: str) -> RegressionRun | None:
        return self._runs.get(run_id)

    async def list_runs(self, tenant_id: str, limit: int = 100) -> list[RegressionRun]:
        runs = [r for r in self._runs.values() if r.tenant_id == tenant_id]
        runs.sort(key=lambda x: x.created_at)
        return runs[:limit]
