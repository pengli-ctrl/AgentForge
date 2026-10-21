"""成本路由模块。"""

from __future__ import annotations

from fastapi import APIRouter, Request

from agentforge.platform.runtime import ServiceContainer


def create_cost_router(container: ServiceContainer) -> APIRouter:
    """创建成本路由。

    Args:
        container: 服务容器。

    Returns:
        处理结果对象。
    """
    router = APIRouter(prefix="/v1/costs", tags=["costs"])

    @router.get("/summary")
    async def cost_summary(request: Request, tenant_id: str) -> dict:
        """处理 GET /summary 请求，查询成本摘要。

        Args:
            request: 当前 HTTP 请求。
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            结构化结果字典。
        """
        container.authenticator.authorize_tenant(request, tenant_id)
        return await container.cost_repository.summary_for_tenant(tenant_id)

    return router
