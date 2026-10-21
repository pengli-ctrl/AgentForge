"""路由模块。"""

from __future__ import annotations

from typing import Any, Protocol
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request

from agentforge.platform.modules.support.application.service import SupportTicketService
from agentforge.platform.modules.support.application.writeback import TicketWritebackService
from agentforge.platform.modules.support.ports import TicketRepository
from agentforge.platform.modules.support.workflows.support_ticket import SupportTicketWorkflow
from agentforge.platform.sdk.ports import AuthenticatorPort, ModuleAccessPort, WorkflowClientPort
from agentforge.platform.sdk.security import verify_event_hmac


class SupportRouterContext(Protocol):
    """客服上下文能力端口协议。"""

    @property
    def authenticator(self) -> AuthenticatorPort:
        """返回认证器。

        Returns:
            认证器结果。
        """
        ...

    @property
    def module_access(self) -> ModuleAccessPort:
        """返回模块访问。

        Returns:
            模块访问结果。
        """
        ...

    @property
    def ticket_service(self) -> SupportTicketService:
        """执行工单服务。

        Returns:
            客服工单服务结果。
        """
        ...

    @property
    def repository(self) -> TicketRepository:
        """执行仓储。

        Returns:
            工单仓储结果。
        """
        ...

    @property
    def workflow_client(self) -> WorkflowClientPort | None:
        """返回工作流客户端。

        Returns:
            工作流客户端无结果。
        """
        ...

    @property
    def ticket_writeback_service(self) -> TicketWritebackService:
        """执行工单写回服务。

        Returns:
            工单写回服务结果。
        """
        ...


def create_support_router(
    container: SupportRouterContext,
    webhook_secret: str = "",
    *,
    prefix: str = "/v1",
) -> APIRouter:
    """创建客服路由。

    Args:
        container: 服务容器。
        webhook_secret: Webhook密钥。
        prefix: 前缀。

    Returns:
        处理结果对象。
    """
    router = APIRouter(prefix=prefix, tags=["support"])

    @router.post("/events/im")
    async def receive_im_event(request: Request, body: dict[str, Any]) -> dict[str, Any]:
        """处理 POST /events/im 请求，接收事件。

        Args:
            request: 当前 HTTP 请求。
            body: 请求体数据。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        tenant_id = body.get("tenant_id")
        if not isinstance(tenant_id, str) or not tenant_id:
            raise HTTPException(status_code=422, detail="tenant_id is required")
        await _authorize_support(container, request, tenant_id)
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
        """处理 POST /workflows/support 请求，启动客服工作流。

        Args:
            request: 当前 HTTP 请求。
            body: 请求体数据。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        tenant_id = body.get("tenant_id")
        if isinstance(tenant_id, str):
            await _authorize_support(container, request, tenant_id)
        if container.workflow_client is None:
            raise HTTPException(
                status_code=503, detail="Temporal workflow client is not configured"
            )
        workflow_id = body.get("workflow_id") or f"support-{uuid4()}"
        try:
            resolved_id = await container.workflow_client.start_workflow(
                SupportTicketWorkflow.run,
                body,
                workflow_id=workflow_id,
                id_prefix="support",
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
        """处理 POST /tickets/{ticket_id}/approve 请求，批准工单。

        Args:
            request: 当前 HTTP 请求。
            ticket_id: 工单 ID。
            body: 请求体数据。

        Returns:
            结构化结果字典。
        """
        return await _apply_approval(container, request, ticket_id, body, "approve")

    @router.post("/tickets/{ticket_id}/reject")
    async def reject_ticket(
        request: Request,
        ticket_id: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        """处理 POST /tickets/{ticket_id}/reject 请求，拒绝工单。

        Args:
            request: 当前 HTTP 请求。
            ticket_id: 工单 ID。
            body: 请求体数据。

        Returns:
            结构化结果字典。
        """
        return await _apply_approval(container, request, ticket_id, body, "reject")

    @router.get("/tickets/{ticket_id}")
    async def get_ticket(request: Request, ticket_id: str, tenant_id: str) -> dict[str, Any]:
        """处理 GET /tickets/{ticket_id} 请求，获取工单。

        Args:
            request: 当前 HTTP 请求。
            ticket_id: 工单 ID。
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        await _authorize_support(container, request, tenant_id)
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
        """处理 POST /tickets/{ticket_id}/review 请求，审核工单。

        Args:
            request: 当前 HTTP 请求。
            ticket_id: 工单 ID。
            body: 请求体数据。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        tenant_id = body.get("tenant_id")
        reviewer_id = body.get("reviewer_id")
        action = body.get("action")
        if not all(isinstance(value, str) and value for value in (tenant_id, reviewer_id, action)):
            raise HTTPException(
                status_code=422,
                detail="tenant_id, reviewer_id and action are required",
            )
        await _authorize_support(container, request, tenant_id)
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
        """处理 POST /tickets/{ticket_id}/reply 请求，发布回复。

        Args:
            request: 当前 HTTP 请求。
            ticket_id: 工单 ID。
            body: 请求体数据。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        tenant_id = body.get("tenant_id")
        reply_text = body.get("text")
        if not isinstance(tenant_id, str):
            raise HTTPException(status_code=422, detail="tenant_id is required")
        await _authorize_support(container, request, tenant_id)
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
        """处理 POST /tickets/{ticket_id}/writeback 请求，提交写回工单。

        Args:
            request: 当前 HTTP 请求。
            ticket_id: 工单 ID。
            body: 请求体数据。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        tenant_id = body.get("tenant_id")
        if not isinstance(tenant_id, str) or not tenant_id:
            raise HTTPException(status_code=422, detail="tenant_id is required")
        await _authorize_support(container, request, tenant_id)
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


async def _authorize_support(
    container: SupportRouterContext,
    request: Request,
    tenant_id: str,
) -> None:
    """授权客服。

    Args:
        container: 服务容器。
        request: 当前 HTTP 请求。
        tenant_id: 租户 ID，用于数据隔离。

    Raises:
        HTTPException: 请求参数、状态或依赖不满足要求时抛出。
    """
    container.authenticator.authorize_tenant(request, tenant_id)
    if not await container.module_access.is_enabled(tenant_id, "support"):
        raise HTTPException(status_code=403, detail="Support module is not enabled for tenant")


async def _apply_approval(
    container: SupportRouterContext,
    request: Request,
    ticket_id: str,
    body: dict[str, Any],
    decision: str,
) -> dict[str, Any]:
    """应用审批。

    Args:
        container: 服务容器。
        request: 当前 HTTP 请求。
        ticket_id: 工单 ID。
        body: 请求体数据。
        decision: 待处理的授权或审批决策。

    Returns:
        结构化结果字典。

    Raises:
        HTTPException: 请求参数、状态或依赖不满足要求时抛出。
    """
    tenant_id = body.get("tenant_id")
    decided_by = body.get("decided_by")
    if not isinstance(tenant_id, str) or not isinstance(decided_by, str):
        raise HTTPException(status_code=422, detail="tenant_id and decided_by are required")
    await _authorize_support(container, request, tenant_id)
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
        await container.workflow_client.signal_workflow(
            workflow_id,
            SupportTicketWorkflow.approve,
            {"decision": decision, "decided_by": decided_by},
        )
    return ticket.model_dump(mode="json")
