from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from agentforge.platform.runtime import ServiceContainer


def create_audit_router(container: ServiceContainer) -> APIRouter:
    router = APIRouter(prefix="/v1/audit", tags=["audit"])

    @router.get("")
    async def list_events(
        request: Request,
        tenant_id: str,
        limit: int = 100,
        resource_id: str | None = None,
    ) -> dict:
        container.authenticator.authorize_tenant(request, tenant_id)
        if container.audit_repository is None:
            raise HTTPException(status_code=503, detail="Audit repository is not configured")
        events = await container.audit_repository.list_events(
            tenant_id=tenant_id,
            limit=limit,
            resource_id=resource_id,
        )
        return {"events": [event.model_dump(mode="json") for event in events]}

    return router
