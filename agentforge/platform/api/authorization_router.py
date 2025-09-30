from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from agentforge.platform.runtime import ServiceContainer


def create_authorization_router(container: ServiceContainer) -> APIRouter:
    """Expose the high-risk authorization gate as an audited API.

    ``POST /v1/authorize`` evaluates whether ``principal`` may run ``action`` on
    a resource and -- when a human-approved ``ticket`` context is supplied --
    enforces the approval boundary. Every check is persisted as an audit event,
    so callers can answer "who executed / why allowed" for high-risk actions.
    """
    router = APIRouter(prefix="/v1/authorize", tags=["authorize"])

    @router.post("")
    async def authorize(
        request: Request,
        body: dict[str, Any],
    ) -> dict:
        tenant_id = body.get("tenant_id")
        principal = body.get("principal")
        action = body.get("action")
        if not isinstance(tenant_id, str) or not tenant_id:
            raise HTTPException(status_code=422, detail="tenant_id is required")
        if not isinstance(principal, str) or not principal:
            raise HTTPException(status_code=422, detail="principal is required")
        if not isinstance(action, str) or not action:
            raise HTTPException(status_code=422, detail="action is required")
        container.authenticator.authorize_tenant(request, tenant_id)
        if container.high_risk_authorizer is None:
            raise HTTPException(status_code=503, detail="authorizer not configured")

        decision = await container.high_risk_authorizer.authorize(
            tenant_id=tenant_id,
            principal=principal,
            action=action,
            resource_type=body.get("resource_type", ""),
            resource_id=body.get("resource_id", ""),
            relation=body.get("relation"),
        )
        return decision.model_dump(mode="json")

    return router
