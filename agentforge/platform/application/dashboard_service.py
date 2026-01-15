"""AgentForge 平台应用服务层：dashboard_service。

本模块实现 dashboard_service 应用服务，编排多个领域对象和基础设施组件完成业务流程。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：DashboardService。
"""

from __future__ import annotations


class DashboardService:
    """DashboardService。

    DashboardService 编排业务流程，协调仓储、模型、策略和外部连接器完成用例。

    主要成员：
    - 方法 attach_trace_recorder()。
    - 方法 recent_traces()。
    - 方法 cost_trend()。
    - 方法 model_distribution()。
    - 方法 quota_snapshot()。
    - 方法 quality_metrics()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    def __init__(self, cost_repository, quota_repository, regression_repository) -> None:
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Args:
            cost_repository: Any，调用方传入的 cost_repository 参数。
            quota_repository: Any，调用方传入的 quota_repository 参数。
            regression_repository: Any，调用方传入的 regression_repository 参数。

        Returns:
            None，函数执行后的结果。
        """
        self._cost = cost_repository
        self._quota = quota_repository
        self._regression = regression_repository
        self._trace_recorder = None

    def attach_trace_recorder(self, trace_recorder) -> None:
        """执行 attach_trace_recorder 对应的逻辑，并返回处理结果。

        Args:
            trace_recorder: Any，调用方传入的 trace_recorder 参数。

        Returns:
            None，函数执行后的结果。
        """
        self._trace_recorder = trace_recorder

    async def recent_traces(self, tenant_id: str | None = None, limit: int = 50) -> dict:
        """执行 recent_traces 对应的逻辑，并返回处理结果。

        Args:
            tenant_id: str | None，调用方传入的 tenant_id 参数。
            limit: int，调用方传入的 limit 参数。

        Returns:
            dict，函数执行后的结果。
        """
        if self._trace_recorder is None:
            return {
                "configured": False,
                "tenant_id": tenant_id or "",
                "traces": [],
                "summary": None,
            }
        return await self._trace_recorder.summary(tenant_id)

    async def cost_trend(self, tenant_id: str, days: int = 30) -> dict:
        """执行 cost_trend 对应的逻辑，并返回处理结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。
            days: int，调用方传入的 days 参数。

        Returns:
            dict，函数执行后的结果。
        """
        daily = await self._cost.daily_summary(tenant_id, days=days)
        return {
            "tenant_id": tenant_id,
            "days": days,
            "total_amount": round(sum(d["amount"] for d in daily), 4),
            "total_requests": sum(d["request_count"] for d in daily),
            "daily": daily,
        }

    async def model_distribution(self, tenant_id: str) -> dict:
        """执行 model_distribution 对应的逻辑，并返回处理结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。

        Returns:
            dict，函数执行后的结果。
        """
        summary = await self._cost.summary_for_tenant(tenant_id)
        by_model = summary.get("by_model", [])
        # 按 cost 降序，便于看板优先展示最贵模型
        by_model = sorted(by_model, key=lambda m: m["amount"], reverse=True)
        total_amount = summary.get("total_amount", 0.0)
        for item in by_model:
            item["share"] = round(item["amount"] / total_amount, 4) if total_amount else 0.0
        return {
            "tenant_id": tenant_id,
            "total_amount": total_amount,
            "total_requests": summary.get("request_count", 0),
            "models": by_model,
        }

    async def quota_snapshot(self, tenant_id: str) -> dict:
        """执行 quota_snapshot 对应的逻辑，并返回处理结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。

        Returns:
            dict，函数执行后的结果。
        """
        quota = None
        if self._quota is not None:
            quota = await self._quota.get(tenant_id)
        used = 0.0
        if self._cost is not None:
            used = await self._cost.total_for_tenant(tenant_id)
        if quota is not None:
            return {
                "tenant_id": tenant_id,
                "configured": True,
                "quota": quota.model_dump(mode="json"),
                "usage": quota.usage_status(used),
                "used": used,
            }
        return {"tenant_id": tenant_id, "configured": False, "used": used}

    async def quality_metrics(self, tenant_id: str, limit: int = 10) -> dict:
        """执行 quality_metrics 对应的逻辑，并返回处理结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。
            limit: int，调用方传入的 limit 参数。

        Returns:
            dict，函数执行后的结果。
        """
        if self._regression is None:
            return {"tenant_id": tenant_id, "configured": False, "runs": [], "recent": None}
        runs = await self._regression.list_runs(tenant_id, limit=limit)
        items = [
            {
                "run_id": r.run_id,
                "candidate_id": r.candidate_id,
                "status": r.status.value,
                "verdict": r.verdict,
                "recall_at_k": r.recall_at_k,
                "citation_accuracy": r.citation_accuracy,
                "classification_accuracy": r.classification_accuracy,
                "priority_accuracy": r.priority_accuracy,
                "structured_output_rate": r.structured_output_rate,
                "high_risk_miss_rate": r.high_risk_miss_rate,
                "created_at": r.created_at.isoformat(),
            }
            for r in runs
        ]
        avg = {}
        if items:
            avg = {
                "recall_at_k": round(sum(i["recall_at_k"] for i in items) / len(items), 4),
                "citation_accuracy": round(
                    sum(i["citation_accuracy"] for i in items) / len(items), 4
                ),
                "classification_accuracy": round(
                    sum(i["classification_accuracy"] for i in items) / len(items), 4
                ),
                "high_risk_miss_rate": round(
                    sum(i["high_risk_miss_rate"] for i in items) / len(items), 4
                ),
            }
        return {
            "tenant_id": tenant_id,
            "configured": bool(items),
            "run_count": len(items),
            "recent": items[0] if items else None,
            "averages": avg,
        }
