"""配额路由模块。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from agentforge.platform.application.ports import CostRepository
from agentforge.platform.domain.tenant_quota import TenantQuota


def create_quota_router(
    quota_repository=None, cost_repository: CostRepository | None = None
) -> APIRouter:
    """创建配额路由。

    Args:
        quota_repository: 配额仓储。
        cost_repository: 成本仓储。

    Returns:
        处理结果对象。
    """
    router = APIRouter(prefix="/v1/quotas", tags=["quotas"])

    @router.put("/{tenant_id}")
    async def upsert_quota(
        tenant_id: str,
        body: dict[str, Any],
    ) -> dict:
        """处理 PUT /{tenant_id} 请求，新建或更新配额。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            body: 请求体数据。

        Returns:
            结构化结果字典。

        Raises:
            RuntimeError: 运行时依赖或状态不满足要求时抛出。
        """
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
        """处理 GET /{tenant_id} 请求，获取配额。

        Args:
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            结构化结果字典。

        Raises:
            RuntimeError: 运行时依赖或状态不满足要求时抛出。
        """
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
        """处理 GET 请求，查询配额。

        Returns:
            结构化结果字典。

        Raises:
            RuntimeError: 运行时依赖或状态不满足要求时抛出。
        """
        if quota_repository is None:
            raise RuntimeError("quota repository not configured")
        quotas = await quota_repository.list()
        return {"quotas": [q.model_dump(mode="json") for q in quotas]}

    @router.delete("/{tenant_id}")
    async def delete_quota(tenant_id: str) -> dict:
        """处理 DELETE /{tenant_id} 请求，删除配额。

        Args:
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            结构化结果字典。

        Raises:
            RuntimeError: 运行时依赖或状态不满足要求时抛出。
        """
        if quota_repository is None:
            raise RuntimeError("quota repository not configured")
        await quota_repository.delete(tenant_id)
        return {"deleted": tenant_id}

    return router
