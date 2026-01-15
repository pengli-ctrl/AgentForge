"""AgentForge 平台 API 层：quota_router。

本模块定义 quota_ 相关 HTTP 接口，负责请求解析、鉴权校验、调用应用服务并组织响应。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要函数：create_quota_router。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from agentforge.platform.application.ports import CostRepository
from agentforge.platform.domain.tenant_quota import TenantQuota


def create_quota_router(
    quota_repository=None, cost_repository: CostRepository | None = None
) -> APIRouter:
    """创建新的业务对象，并返回调用方需要的结果。

    Args:
        quota_repository: Any，调用方传入的 quota_repository 参数。
        cost_repository: CostRepository | None，调用方传入的 cost_repository 参数。

    Returns:
        APIRouter，函数执行后的结果。

    Raises:
        RuntimeError: 当输入、状态或外部依赖不满足要求时抛出。
    """
    router = APIRouter(prefix="/v1/quotas", tags=["quotas"])

    @router.put("/{tenant_id}")
    async def upsert_quota(
        tenant_id: str,
        body: dict[str, Any],
    ) -> dict:
        """执行 upsert_quota 对应的逻辑，并返回处理结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。
            body: dict[str, Any]，调用方传入的 body 参数。

        Returns:
            dict，函数执行后的结果。

        Raises:
            RuntimeError: 当输入、状态或外部依赖不满足要求时抛出。
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
        """读取并返回指定数据，并返回调用方需要的结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。

        Returns:
            dict，函数执行后的结果。

        Raises:
            RuntimeError: 当输入、状态或外部依赖不满足要求时抛出。
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
        """查询并返回列表结果，并返回调用方需要的结果。

        Returns:
            dict，函数执行后的结果。

        Raises:
            RuntimeError: 当输入、状态或外部依赖不满足要求时抛出。
        """
        if quota_repository is None:
            raise RuntimeError("quota repository not configured")
        quotas = await quota_repository.list()
        return {"quotas": [q.model_dump(mode="json") for q in quotas]}

    @router.delete("/{tenant_id}")
    async def delete_quota(tenant_id: str) -> dict:
        """删除指定数据，并返回调用方需要的结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。

        Returns:
            dict，函数执行后的结果。

        Raises:
            RuntimeError: 当输入、状态或外部依赖不满足要求时抛出。
        """
        if quota_repository is None:
            raise RuntimeError("quota repository not configured")
        await quota_repository.delete(tenant_id)
        return {"deleted": tenant_id}

    return router
