"""路由模块。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from agentforge.platform.runtime import ServiceContainer


def create_authorization_router(container: ServiceContainer) -> APIRouter:
    """创建授权路由。

    Args:
        container: 服务容器。

    Returns:
        处理结果对象。
    """
    router = APIRouter(prefix="/v1/authorize", tags=["authorize"])

    @router.post("")
    async def authorize(
        request: Request,
        body: dict[str, Any],
    ) -> dict:
        """执行授权决策。

        Args:
            request: 当前 HTTP 请求。
            body: 请求体数据。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
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
        decision = await container.authorization_service.authorize(
            tenant_id=tenant_id,
            principal=principal,
            action=action,
            resource_type=body.get("resource_type", ""),
            resource_id=body.get("resource_id", ""),
            relation=body.get("relation"),
        )
        return decision.model_dump(mode="json")

    return router
