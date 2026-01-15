"""AgentForge 平台 API 层：support_router。

本模块定义 support_ 相关 HTTP 接口，负责请求解析、鉴权校验、调用应用服务并组织响应。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要函数：create_support_router。
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request

from agentforge.platform.api.security import verify_event_hmac
from agentforge.platform.runtime import ServiceContainer


def create_support_router(
    container: ServiceContainer,
    webhook_secret: str = "",
) -> APIRouter:
    """创建新的业务对象，并返回调用方需要的结果。

    Args:
        container: ServiceContainer，调用方传入的 container 参数。
        webhook_secret: str，调用方传入的 webhook_secret 参数。

    Returns:
        APIRouter，函数执行后的结果。

    Raises:
        HTTPException: 当输入、状态或外部依赖不满足要求时抛出。
    """
    router = APIRouter(prefix="/v1", tags=["support"])

    @router.post("/events/im")
    async def receive_im_event(request: Request, body: dict[str, Any]) -> dict[str, Any]:
        """执行 receive_im_event 对应的逻辑，并返回处理结果。

        Args:
            request: Request，调用方传入的 request 参数。
            body: dict[str, Any]，调用方传入的 body 参数。

        Returns:
            dict[str, Any]，函数执行后的结果。

        Raises:
            HTTPException: 当输入、状态或外部依赖不满足要求时抛出。
        """
        tenant_id = body.get("tenant_id")
        if not isinstance(tenant_id, str) or not tenant_id:
            raise HTTPException(status_code=422, detail="tenant_id is required")
        container.authenticator.authorize_tenant(request, tenant_id)
        raw_body = await request.body()
        provided = request.headers.get("X-Webhook-Signature", "")
        if not verify_event_hmac(raw_body, webhook_secret, provided):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")
        try:
            ticket = await container.ticket_service.create_from_event(body)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return ticket.model_dump(mode="json")

    @router.post("/workflows/support")
    async def start_support_workflow(request: Request, body: dict[str, Any]) -> dict[str, str]:
        """执行 start_support_workflow 对应的逻辑，并返回处理结果。

        Args:
            request: Request，调用方传入的 request 参数。
            body: dict[str, Any]，调用方传入的 body 参数。

        Returns:
            dict[str, str]，函数执行后的结果。

        Raises:
            HTTPException: 当输入、状态或外部依赖不满足要求时抛出。
        """
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
        """执行 approve_ticket 对应的逻辑，并返回处理结果。

        Args:
            request: Request，调用方传入的 request 参数。
            ticket_id: str，调用方传入的 ticket_id 参数。
            body: dict[str, Any]，调用方传入的 body 参数。

        Returns:
            dict[str, Any]，函数执行后的结果。
        """
        return await _apply_approval(container, request, ticket_id, body, "approve")

    @router.post("/tickets/{ticket_id}/reject")
    async def reject_ticket(
        request: Request,
        ticket_id: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        """执行 reject_ticket 对应的逻辑，并返回处理结果。

        Args:
            request: Request，调用方传入的 request 参数。
            ticket_id: str，调用方传入的 ticket_id 参数。
            body: dict[str, Any]，调用方传入的 body 参数。

        Returns:
            dict[str, Any]，函数执行后的结果。
        """
        return await _apply_approval(container, request, ticket_id, body, "reject")

    @router.get("/tickets/{ticket_id}")
    async def get_ticket(request: Request, ticket_id: str, tenant_id: str) -> dict[str, Any]:
        """读取并返回指定数据，并返回调用方需要的结果。

        Args:
            request: Request，调用方传入的 request 参数。
            ticket_id: str，调用方传入的 ticket_id 参数。
            tenant_id: str，调用方传入的 tenant_id 参数。

        Returns:
            dict[str, Any]，函数执行后的结果。

        Raises:
            HTTPException: 当输入、状态或外部依赖不满足要求时抛出。
        """
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
        """执行 review_ticket 对应的逻辑，并返回处理结果。

        Args:
            request: Request，调用方传入的 request 参数。
            ticket_id: str，调用方传入的 ticket_id 参数。
            body: dict[str, Any]，调用方传入的 body 参数。

        Returns:
            dict[str, Any]，函数执行后的结果。

        Raises:
            HTTPException: 当输入、状态或外部依赖不满足要求时抛出。
        """
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
        """执行 publish_reply 对应的逻辑，并返回处理结果。

        Args:
            request: Request，调用方传入的 request 参数。
            ticket_id: str，调用方传入的 ticket_id 参数。
            body: dict[str, Any]，调用方传入的 body 参数。

        Returns:
            dict[str, Any]，函数执行后的结果。

        Raises:
            HTTPException: 当输入、状态或外部依赖不满足要求时抛出。
        """
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

    @router.post("/tickets/{ticket_id}/writeback")
    async def writeback_ticket(
        request: Request,
        ticket_id: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        """执行 writeback_ticket 对应的逻辑，并返回处理结果。

        Args:
            request: Request，调用方传入的 request 参数。
            ticket_id: str，调用方传入的 ticket_id 参数。
            body: dict[str, Any]，调用方传入的 body 参数。

        Returns:
            dict[str, Any]，函数执行后的结果。

        Raises:
            HTTPException: 当输入、状态或外部依赖不满足要求时抛出。
        """
        tenant_id = body.get("tenant_id")
        if not isinstance(tenant_id, str) or not tenant_id:
            raise HTTPException(status_code=422, detail="tenant_id is required")
        container.authenticator.authorize_tenant(request, tenant_id)
        ticket = await container.repository.get(tenant_id, ticket_id)
        if ticket is None:
            raise HTTPException(status_code=404, detail="Ticket not found")
        action = body.get("action") or "ticket.writeback"
        actor = body.get("actor") or "support-writeback"
        try:
            data = await container.ticket_writeback_service.write_back(ticket, action, actor=actor)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return {"ticket_id": ticket_id, "ok": True, "data": data}

    return router


async def _apply_approval(
    container: ServiceContainer,
    request: Request,
    ticket_id: str,
    body: dict[str, Any],
    decision: str,
) -> dict[str, Any]:
    """执行 _apply_approval 对应的逻辑，并返回处理结果。

    Args:
        container: ServiceContainer，调用方传入的 container 参数。
        request: Request，调用方传入的 request 参数。
        ticket_id: str，调用方传入的 ticket_id 参数。
        body: dict[str, Any]，调用方传入的 body 参数。
        decision: str，调用方传入的 decision 参数。

    Returns:
        dict[str, Any]，函数执行后的结果。

    Raises:
        HTTPException: 当输入、状态或外部依赖不满足要求时抛出。
    """
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
