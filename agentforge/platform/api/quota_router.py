from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from agentforge.platform.application.ports import CostRepository
from agentforge.platform.domain.tenant_quota import TenantQuota


def create_quota_router(
    quota_repository=None, cost_repository: CostRepository | None = None
) -> APIRouter:
    router = APIRouter(prefix="/v1/quotas", tags=["quotas"])

    @router.put("/{tenant_id}")
    async def upsert_quota(
        tenant_id: str,
        body: dict[str, Any],
    ) -> dict:
        if quota_repository is None:
            raise RuntimeError("quota repository not configured")
        quota = TenantQuota(
            tenant_id=tenant_id,
            monthly_limit=float(body.get("monthly_limit", 0.0)),
            warning_threshold=float(body.get("warning_threshold", 0.8)),
            hard_limit=float(body.get("hard_limit", 1.0)),
            enabled=bool(body.get("enabled", True)),
        )
        await quota_repository.upsert(quota)
        return quota.model_dump(mode="json")

    @router.get("/{tenant_id}")
    async def get_quota(tenant_id: str) -> dict:
        if quota_repository is None:
            raise RuntimeError("quota repository not configured")
        quota = await quota_repository.get(tenant_id)
        if quota is None:
            return {"tenant_id": tenant_id, "configured": False}
        result = quota.model_dump(mode="json")
        result["configured"] = True
        if cost_repository is not None:
            used = await cost_repository.total_for_tenant(tenant_id)
            result["usage"] = quota.usage_status(used)
        return result

    @router.get("")
    async def list_quotas() -> dict:
        if quota_repository is None:
            raise RuntimeError("quota repository not configured")
        quotas = await quota_repository.list()
        return {"quotas": [q.model_dump(mode="json") for q in quotas]}

    @router.delete("/{tenant_id}")
    async def delete_quota(tenant_id: str) -> dict:
        if quota_repository is None:
            raise RuntimeError("quota repository not configured")
        await quota_repository.delete(tenant_id)
        return {"deleted": tenant_id}

    return router
