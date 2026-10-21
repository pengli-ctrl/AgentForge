"""记忆回归仓储模块。"""

from __future__ import annotations

from agentforge.platform.domain.regression import GoldenItem, QualityReport, RegressionRun


class MemoryRegressionRepository:
    """回归仓储，负责持久化读写。"""

    def __init__(self) -> None:
        """初始化 MemoryRegressionRepository。"""
        self._golden: dict[str, GoldenItem] = {}
        self._runs: dict[str, RegressionRun] = {}

    async def save_golden(self, item: GoldenItem) -> None:
        """保存基准。

        Args:
            item: 条目。
        """
        self._golden[item.item_id] = item

    async def list_golden(self, tenant_id: str, limit: int = 100) -> list[GoldenItem]:
        """查询基准。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            limit: 返回记录的最大数量。

        Returns:
            结果列表。
        """
        items = [i for i in self._golden.values() if i.tenant_id == tenant_id]
        items.sort(key=lambda x: x.created_at)
        return items[:limit]

    async def save_run(self, run: RegressionRun) -> None:
        """保存运行。

        Args:
            run: 运行。
        """
        self._runs[run.run_id] = run

    async def save_report(self, report: QualityReport) -> None:
        # 报告并入对应 run 的元信息由调用方管理，此处直接耦合 metric 摘要便于内存断言。
        """保存报告。

        Args:
            report: 报告。
        """
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
        """获取运行。

        Args:
            run_id: 运行记录 ID。

        Returns:
            回归运行无结果。
        """
        return self._runs.get(run_id)

    async def list_runs(self, tenant_id: str, limit: int = 100) -> list[RegressionRun]:
        """查询运行记录。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            limit: 返回记录的最大数量。

        Returns:
            结果列表。
        """
        runs = [r for r in self._runs.values() if r.tenant_id == tenant_id]
        runs.sort(key=lambda x: x.created_at)
        return runs[:limit]
