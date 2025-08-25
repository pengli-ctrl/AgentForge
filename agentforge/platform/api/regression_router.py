from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from agentforge.platform.domain.quality import ReleaseCandidate
from agentforge.platform.domain.regression import GoldenItem
from agentforge.platform.runtime import ServiceContainer


def create_regression_router(container: ServiceContainer) -> APIRouter:
    router = APIRouter(prefix="/v1/regression", tags=["regression"])

    @router.post("/golden")
    async def add_golden(request: Request, item: GoldenItem) -> dict[str, str]:
        """新增/覆盖一条 Golden Dataset 离线回归样本。"""
        container.authenticator.authorize_tenant(request, item.tenant_id)
        await container.regression_repository.save_golden(item)
        return {"item_id": item.item_id, "status": "saved"}

    @router.get("/golden")
    async def list_golden(
        request: Request, tenant_id: str, limit: int = Query(default=100)
    ) -> dict[str, Any]:
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
        """对租户的 Golden Dataset 执行一次离线回归，返回质量报告并持久化。"""
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
        container.authenticator.authorize_tenant(request, tenant_id)
        runs = await container.regression_repository.list_runs(tenant_id, limit=limit)
        return {"runs": [r.model_dump(mode="json") for r in runs]}

    @router.get("/runs/{run_id}")
    async def get_run(request: Request, run_id: str, tenant_id: str) -> dict[str, Any]:
        container.authenticator.authorize_tenant(request, tenant_id)
        run = await container.regression_repository.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Regression run not found")
        return run.model_dump(mode="json")

    return router
