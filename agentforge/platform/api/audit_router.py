from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from agentforge.platform.runtime import ServiceContainer


def create_audit_router(container: ServiceContainer) -> APIRouter:
    router = APIRouter(prefix="/v1/audit", tags=["audit"])

    @router.get("")
    async def list_events(
        request: Request,
        tenant_id: str | None = None,
        limit: int = 100,
        resource_id: str | None = None,
        action: str | None = None,
        actor_id: str | None = None,
        resource_type: str | None = None,
        cursor: str | None = None,
    ) -> dict:
        if tenant_id is None:
            container.authenticator.authorize_admin(request)
        else:
            container.authenticator.authorize_tenant(request, tenant_id)
        if container.audit_repository is None:
            raise HTTPException(status_code=503, detail="Audit repository is not configured")
        events, next_cursor = await container.audit_repository.query_events(
            tenant_id=tenant_id,
            limit=limit,
            resource_id=resource_id,
            action=action,
            actor_id=actor_id,
            resource_type=resource_type,
            cursor=cursor,
        )
        return {
            "events": [event.model_dump(mode="json") for event in events],
            "next_cursor": next_cursor,
        }

    return router
