"""AgentForge 平台 API 层：authorization_router。

本模块定义 authorization_ 相关 HTTP 接口，负责请求解析、鉴权校验、调用应用服务并组织响应。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要函数：create_authorization_router。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from agentforge.platform.runtime import ServiceContainer


def create_authorization_router(container: ServiceContainer) -> APIRouter:
    """创建新的业务对象，并返回调用方需要的结果。

    Args:
        container: ServiceContainer，调用方传入的 container 参数。

    Returns:
        APIRouter，函数执行后的结果。

    Raises:
        HTTPException: 当输入、状态或外部依赖不满足要求时抛出。
    """
    router = APIRouter(prefix="/v1/authorize", tags=["authorize"])

    @router.post("")
    async def authorize(
        request: Request,
        body: dict[str, Any],
    ) -> dict:
        """执行 authorize 对应的逻辑，并返回处理结果。

        Args:
            request: Request，调用方传入的 request 参数。
            body: dict[str, Any]，调用方传入的 body 参数。

        Returns:
            dict，函数执行后的结果。

        Raises:
            HTTPException: 当输入、状态或外部依赖不满足要求时抛出。
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
