from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from agentforge.platform.runtime import ServiceContainer


def create_evaluation_router(container: ServiceContainer) -> APIRouter:
    router = APIRouter(prefix="/v1/evaluations", tags=["evaluations"])

    @router.get("/summary")
    async def summary(request: Request, tenant_id: str) -> dict:
        container.authenticator.authorize_tenant(request, tenant_id)
        if container.evaluation_repository is None:
            raise HTTPException(status_code=503, detail="Evaluation repository is not configured")
        return await container.evaluation_repository.summary(tenant_id)

    @router.get("/samples")
    async def list_samples(
        request: Request,
        tenant_id: str,
        limit: int = 100,
        action: str | None = None,
    ) -> dict:
        container.authenticator.authorize_tenant(request, tenant_id)
        if container.evaluation_repository is None:
            raise HTTPException(status_code=503, detail="Evaluation repository is not configured")
        samples = await container.evaluation_repository.list_samples(
            tenant_id=tenant_id,
            limit=limit,
            action=action,
        )
        return {"samples": [sample.model_dump(mode="json") for sample in samples]}

    return router
