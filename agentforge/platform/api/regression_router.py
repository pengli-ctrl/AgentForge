"""AgentForge 平台 API 层：regression_router。

本模块定义 regression_ 相关 HTTP 接口，负责请求解析、鉴权校验、调用应用服务并组织响应。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要函数：create_regression_router。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from agentforge.platform.domain.quality import ReleaseCandidate
from agentforge.platform.domain.regression import GoldenItem
from agentforge.platform.runtime import ServiceContainer


def create_regression_router(container: ServiceContainer) -> APIRouter:
    """创建新的业务对象，并返回调用方需要的结果。

    Args:
        container: ServiceContainer，调用方传入的 container 参数。

    Returns:
        APIRouter，函数执行后的结果。

    Raises:
        HTTPException: 当输入、状态或外部依赖不满足要求时抛出。
    """
    router = APIRouter(prefix="/v1/regression", tags=["regression"])

    @router.post("/golden")
    async def add_golden(request: Request, item: GoldenItem) -> dict[str, str]:
        """新增业务数据，并返回调用方需要的结果。

        Args:
            request: Request，调用方传入的 request 参数。
            item: GoldenItem，调用方传入的 item 参数。

        Returns:
            dict[str, str]，函数执行后的结果。
        """
        container.authenticator.authorize_tenant(request, item.tenant_id)
        await container.regression_repository.save_golden(item)
        return {"item_id": item.item_id, "status": "saved"}

    @router.get("/golden")
    async def list_golden(
        request: Request, tenant_id: str, limit: int = Query(default=100)
    ) -> dict[str, Any]:
        """查询并返回列表结果，并返回调用方需要的结果。

        Args:
            request: Request，调用方传入的 request 参数。
            tenant_id: str，调用方传入的 tenant_id 参数。
            limit: int，调用方传入的 limit 参数。

        Returns:
            dict[str, Any]，函数执行后的结果。
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
        """执行完整流程，并返回调用方需要的结果。

        Args:
            request: Request，调用方传入的 request 参数。
            candidate: ReleaseCandidate，调用方传入的 candidate 参数。
            k: int，调用方传入的 k 参数。
            rerank: bool，调用方传入的 rerank 参数。

        Returns:
            dict[str, Any]，函数执行后的结果。

        Raises:
            HTTPException: 当输入、状态或外部依赖不满足要求时抛出。
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
        """查询并返回列表结果，并返回调用方需要的结果。

        Args:
            request: Request，调用方传入的 request 参数。
            tenant_id: str，调用方传入的 tenant_id 参数。
            limit: int，调用方传入的 limit 参数。

        Returns:
            dict[str, Any]，函数执行后的结果。
        """
        container.authenticator.authorize_tenant(request, tenant_id)
        runs = await container.regression_repository.list_runs(tenant_id, limit=limit)
        return {"runs": [r.model_dump(mode="json") for r in runs]}

    @router.get("/runs/{run_id}")
    async def get_run(request: Request, run_id: str, tenant_id: str) -> dict[str, Any]:
        """读取并返回指定数据，并返回调用方需要的结果。

        Args:
            request: Request，调用方传入的 request 参数。
            run_id: str，调用方传入的 run_id 参数。
            tenant_id: str，调用方传入的 tenant_id 参数。

        Returns:
            dict[str, Any]，函数执行后的结果。

        Raises:
            HTTPException: 当输入、状态或外部依赖不满足要求时抛出。
        """
        container.authenticator.authorize_tenant(request, tenant_id)
        run = await container.regression_repository.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Regression run not found")
        return run.model_dump(mode="json")

    return router
