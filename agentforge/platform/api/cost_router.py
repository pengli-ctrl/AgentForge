"""AgentForge 平台 API 层：cost_router。

本模块定义 cost_ 相关 HTTP 接口，负责请求解析、鉴权校验、调用应用服务并组织响应。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要函数：create_cost_router。
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from agentforge.platform.runtime import ServiceContainer


def create_cost_router(container: ServiceContainer) -> APIRouter:
    """创建新的业务对象，并返回调用方需要的结果。

    Args:
        container: ServiceContainer，调用方传入的 container 参数。

    Returns:
        APIRouter，函数执行后的结果。
    """
    router = APIRouter(prefix="/v1/costs", tags=["costs"])

    @router.get("/summary")
    async def cost_summary(request: Request, tenant_id: str) -> dict:
        """执行 cost_summary 对应的逻辑，并返回处理结果。

        Args:
            request: Request，调用方传入的 request 参数。
            tenant_id: str，调用方传入的 tenant_id 参数。

        Returns:
            dict，函数执行后的结果。
        """
        container.authenticator.authorize_tenant(request, tenant_id)
        return await container.cost_repository.summary_for_tenant(tenant_id)

    return router
