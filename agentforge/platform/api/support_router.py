from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request

from agentforge.platform.runtime import ServiceContainer


def create_support_router(container: ServiceContainer) -> APIRouter:
    router = APIRouter(prefix="/v1", tags=["support"])

    @router.post("/events/im")
    async def receive_im_event(request: Request, body: dict[str, Any]) -> dict[str, Any]:
        tenant_id = body.get("tenant_id")
        if isinstance(tenant_id, str):
            container.authenticator.authorize_tenant(request, tenant_id)
        try:
            ticket = await container.ticket_service.create_from_event(body)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return ticket.model_dump(mode="json")

    @router.post("/workflows/support")
    async def start_support_workflow(request: Request, body: dict[str, Any]) -> dict[str, str]:
        tenant_id = body.get("tenant_id")
        if isinstance(tenant_id, str):
            container.authenticator.authorize_tenant(request, tenant_id)
        if container.workflow_client is None:
            raise HTTPException(
                status_code=503, detail="Temporal workflow client is not configured"
            )
        workflow_id = body.get("workflow_id") or f"support-{uuid4()}"
        try:
            resolved_id = await container.workflow_client.start_support_workflow(
                body,
                workflow_id=workflow_id,
            )
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return {"workflow_id": resolved_id}

    @router.post("/tickets/{ticket_id}/approve")
    async def approve_ticket(
        request: Request,
        ticket_id: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        return await _apply_approval(container, request, ticket_id, body, "approve")

    @router.post("/tickets/{ticket_id}/reject")
    async def reject_ticket(
        request: Request,
        ticket_id: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        return await _apply_approval(container, request, ticket_id, body, "reject")

    @router.get("/tickets/{ticket_id}")
    async def get_ticket(request: Request, ticket_id: str, tenant_id: str) -> dict[str, Any]:
        container.authenticator.authorize_tenant(request, tenant_id)
        ticket = await container.repository.get(tenant_id, ticket_id)
        if ticket is None:
            raise HTTPException(status_code=404, detail="Ticket not found")
        return ticket.model_dump(mode="json")

    @router.post("/tickets/{ticket_id}/review")
    async def review_ticket(
        request: Request,
        ticket_id: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        tenant_id = body.get("tenant_id")
        reviewer_id = body.get("reviewer_id")
        action = body.get("action")
        if not all(isinstance(value, str) and value for value in (tenant_id, reviewer_id, action)):
            raise HTTPException(
                status_code=422,
                detail="tenant_id, reviewer_id and action are required",
            )
        container.authenticator.authorize_tenant(request, tenant_id)
        try:
            ticket = await container.ticket_service.review_draft(
                tenant_id=tenant_id,
                ticket_id=ticket_id,
                action=action,
                reviewer_id=reviewer_id,
                edited_text=body.get("edited_text"),
                reason=body.get("reason"),
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return ticket.model_dump(mode="json")

    @router.post("/tickets/{ticket_id}/reply")
    async def publish_reply(
        request: Request,
        ticket_id: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        tenant_id = body.get("tenant_id")
        reply_text = body.get("text")
        if not isinstance(tenant_id, str):
            raise HTTPException(status_code=422, detail="tenant_id is required")
        container.authenticator.authorize_tenant(request, tenant_id)
        if reply_text is not None and (not isinstance(reply_text, str) or not reply_text.strip()):
            raise HTTPException(status_code=422, detail="text is required")
        try:
            ticket = await container.ticket_service.publish_reply(
                tenant_id=tenant_id,
                ticket_id=ticket_id,
                text=reply_text.strip() if isinstance(reply_text, str) else None,
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return ticket.model_dump(mode="json")

    return router


async def _apply_approval(
    container: ServiceContainer,
    request: Request,
    ticket_id: str,
    body: dict[str, Any],
    decision: str,
) -> dict[str, Any]:
    tenant_id = body.get("tenant_id")
    decided_by = body.get("decided_by")
    if not isinstance(tenant_id, str) or not isinstance(decided_by, str):
        raise HTTPException(status_code=422, detail="tenant_id and decided_by are required")
    container.authenticator.authorize_tenant(request, tenant_id)
    try:
        ticket = await container.ticket_service.apply_approval(
            tenant_id=tenant_id,
            ticket_id=ticket_id,
            decision=decision,
            decided_by=decided_by,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    workflow_id = body.get("workflow_id")
    if isinstance(workflow_id, str) and workflow_id and container.workflow_client is not None:
        await container.workflow_client.signal_approval(
            workflow_id=workflow_id,
            decision=decision,
            decided_by=decided_by,
        )
    return ticket.model_dump(mode="json")
