"""AgentForge 平台 API 层：audit_router。

本模块定义 audit_ 相关 HTTP 接口，负责请求解析、鉴权校验、调用应用服务并组织响应。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要函数：create_audit_router。
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from agentforge.platform.runtime import ServiceContainer


def create_audit_router(container: ServiceContainer) -> APIRouter:
    """创建新的业务对象，并返回调用方需要的结果。

    Args:
        container: ServiceContainer，调用方传入的 container 参数。

    Returns:
        APIRouter，函数执行后的结果。

    Raises:
        HTTPException: 当输入、状态或外部依赖不满足要求时抛出。
    """
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
        """查询并返回列表结果，并返回调用方需要的结果。

        Args:
            request: Request，调用方传入的 request 参数。
            tenant_id: str | None，调用方传入的 tenant_id 参数。
            limit: int，调用方传入的 limit 参数。
            resource_id: str | None，调用方传入的 resource_id 参数。
            action: str | None，调用方传入的 action 参数。
            actor_id: str | None，调用方传入的 actor_id 参数。
            resource_type: str | None，调用方传入的 resource_type 参数。
            cursor: str | None，调用方传入的 cursor 参数。

        Returns:
            dict，函数执行后的结果。

        Raises:
            HTTPException: 当输入、状态或外部依赖不满足要求时抛出。
        """
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
