"""回归路由模块。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from agentforge.platform.domain.quality import ReleaseCandidate
from agentforge.platform.domain.regression import GoldenItem
from agentforge.platform.runtime import ServiceContainer


def create_regression_router(container: ServiceContainer) -> APIRouter:
    """创建回归路由。

    Args:
        container: 服务容器。

    Returns:
        处理结果对象。
    """
    router = APIRouter(prefix="/v1/regression", tags=["regression"])

    @router.post("/golden")
    async def add_golden(request: Request, item: GoldenItem) -> dict[str, str]:
        """处理 POST /golden 请求，添加基准。

        Args:
            request: 当前 HTTP 请求。
            item: 条目。

        Returns:
            结构化结果字典。
        """
        container.authenticator.authorize_tenant(request, item.tenant_id)
        await container.regression_repository.save_golden(item)
        return {"item_id": item.item_id, "status": "saved"}

    @router.get("/golden")
    async def list_golden(
        request: Request, tenant_id: str, limit: int = Query(default=100)
    ) -> dict[str, Any]:
        """处理 GET /golden 请求，查询基准。

        Args:
            request: 当前 HTTP 请求。
            tenant_id: 租户 ID，用于数据隔离。
            limit: 返回记录的最大数量。

        Returns:
            结构化结果字典。
        """
        container.authenticator.authorize_tenant(request, tenant_id)
        items = await container.regression_repository.list_golden(tenant_id, limit=limit)
        return {"items": [i.model_dump(mode="json") for i in items]}

    @router.post("/run")
    async def run_regression(
        request: Request,
        candidate: ReleaseCandidate,
        k: int = Query(default=5),
        rerank: bool = Query(default=True),
    ) -> dict[str, Any]:
        """处理 POST /run 请求，运行回归。

        Args:
            request: 当前 HTTP 请求。
            candidate: 候选结果。
            k: 返回结果数量上限。
            rerank: 重排。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        container.authenticator.authorize_tenant(request, candidate.tenant_id)
        if container.regression_runner is None:
            raise HTTPException(status_code=503, detail="Regression runner is not configured")
        report = await container.regression_runner.run(
            tenant_id=candidate.tenant_id,
            candidate=candidate,
            k=k,
            rerank=rerank,
        )
        return report.model_dump(mode="json")

    @router.get("/runs")
    async def list_runs(
        request: Request,
        tenant_id: str,
        limit: int = Query(default=100),
    ) -> dict[str, Any]:
        """处理 GET /runs 请求，查询运行记录。

        Args:
            request: 当前 HTTP 请求。
            tenant_id: 租户 ID，用于数据隔离。
            limit: 返回记录的最大数量。

        Returns:
            结构化结果字典。
        """
        container.authenticator.authorize_tenant(request, tenant_id)
        runs = await container.regression_repository.list_runs(tenant_id, limit=limit)
        return {"runs": [r.model_dump(mode="json") for r in runs]}

    @router.get("/runs/{run_id}")
    async def get_run(request: Request, run_id: str, tenant_id: str) -> dict[str, Any]:
        """处理 GET /runs/{run_id} 请求，获取运行。

        Args:
            request: 当前 HTTP 请求。
            run_id: 运行记录 ID。
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        container.authenticator.authorize_tenant(request, tenant_id)
        run = await container.regression_repository.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Regression run not found")
        return run.model_dump(mode="json")

    return router
