"""AgentForge 平台基础设施层：memory_regression_repository。

本模块提供 memory_regression_repository 的内存实现，用于单元测试、本地开发和离线验证。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：MemoryRegressionRepository。
"""

from __future__ import annotations

from agentforge.platform.domain.regression import GoldenItem, QualityReport, RegressionRun


class MemoryRegressionRepository:
    """MemoryRegressionRepository。

    MemoryRegressionRepository 负责数据读写，并确保租户隔离、事务一致性和持久化细节不泄漏到应用层。

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

    def __init__(self) -> None:
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Returns:
            None，函数执行后的结果。
        """
        self._golden: dict[str, GoldenItem] = {}
        self._runs: dict[str, RegressionRun] = {}

    async def save_golden(self, item: GoldenItem) -> None:
        """保存业务数据，并返回调用方需要的结果。

        Args:
            item: GoldenItem，调用方传入的 item 参数。

        Returns:
            None，函数执行后的结果。
        """
        self._golden[item.item_id] = item

    async def list_golden(self, tenant_id: str, limit: int = 100) -> list[GoldenItem]:
        """查询并返回列表结果，并返回调用方需要的结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。
            limit: int，调用方传入的 limit 参数。

        Returns:
            list[GoldenItem]，函数执行后的结果。
        """
        items = [i for i in self._golden.values() if i.tenant_id == tenant_id]
        items.sort(key=lambda x: x.created_at)
        return items[:limit]

    async def save_run(self, run: RegressionRun) -> None:
        """保存业务数据，并返回调用方需要的结果。

        Args:
            run: RegressionRun，调用方传入的 run 参数。

        Returns:
            None，函数执行后的结果。
        """
        self._runs[run.run_id] = run

    async def save_report(self, report: QualityReport) -> None:
        # 报告并入对应 run 的元信息由调用方管理，此处直接耦合 metric 摘要便于内存断言。
        """保存业务数据，并返回调用方需要的结果。

        Args:
            report: QualityReport，调用方传入的 report 参数。

        Returns:
            None，函数执行后的结果。
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
        """读取并返回指定数据，并返回调用方需要的结果。

        Args:
            run_id: str，调用方传入的 run_id 参数。

        Returns:
            RegressionRun | None，函数执行后的结果。
        """
        return self._runs.get(run_id)

    async def list_runs(self, tenant_id: str, limit: int = 100) -> list[RegressionRun]:
        """查询并返回列表结果，并返回调用方需要的结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。
            limit: int，调用方传入的 limit 参数。

        Returns:
            list[RegressionRun]，函数执行后的结果。
        """
        runs = [r for r in self._runs.values() if r.tenant_id == tenant_id]
        runs.sort(key=lambda x: x.created_at)
        return runs[:limit]
