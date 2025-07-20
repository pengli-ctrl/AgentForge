from __future__ import annotations

from fastapi import APIRouter, Request

from agentforge.platform.runtime import ServiceContainer


def create_cost_router(container: ServiceContainer) -> APIRouter:
    router = APIRouter(prefix="/v1/costs", tags=["costs"])

    @router.get("/summary")
    async def cost_summary(request: Request, tenant_id: str) -> dict:
        container.authenticator.authorize_tenant(request, tenant_id)
        return await container.cost_repository.summary_for_tenant(tenant_id)

    return router
