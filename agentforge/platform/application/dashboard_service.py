from __future__ import annotations


class DashboardService:
    """Admin console dashboard aggregations: cost trend, model distribution,
    per-tenant quota snapshot and regression-derived quality metrics.

    Read-only, tenant-scoped; delegates to the injected repositories so it
    works against both memory and SQLAlchemy backends.
    """

    def __init__(self, cost_repository, quota_repository, regression_repository) -> None:
        self._cost = cost_repository
        self._quota = quota_repository
        self._regression = regression_repository

    async def cost_trend(self, tenant_id: str, days: int = 30) -> dict:
        daily = await self._cost.daily_summary(tenant_id, days=days)
        return {
            "tenant_id": tenant_id,
            "days": days,
            "total_amount": round(sum(d["amount"] for d in daily), 4),
            "total_requests": sum(d["request_count"] for d in daily),
            "daily": daily,
        }

    async def model_distribution(self, tenant_id: str) -> dict:
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
