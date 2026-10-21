"""路由模块。"""

from __future__ import annotations

from typing import Any

from agentforge_module_template.application.service import AssetService
from fastapi import APIRouter, HTTPException, Query, Request

from agentforge.platform.sdk.ports import AuthenticatorPort, ModuleAccessPort


def create_asset_router(
    service: AssetService,
    *,
    authenticator: AuthenticatorPort,
    module_access: ModuleAccessPort,
) -> APIRouter:
    """创建资产路由。

    Args:
        service: 服务。
        authenticator: 认证器实例。
        module_access: 模块访问。

    Returns:
        处理结果对象。
    """
    router = APIRouter(tags=["demo-asset"])

    @router.post("/assets")
    async def create_asset(request: Request, body: dict[str, Any]) -> dict[str, Any]:
        """处理 POST /assets 请求，创建资产。

        Args:
            request: 当前 HTTP 请求。
            body: 请求体数据。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        tenant_id = _tenant_id(body)
        await _authorize(request, tenant_id, authenticator, module_access)
        try:
            asset = await service.create(
                tenant_id=tenant_id,
                name=str(body.get("name") or ""),
                created_by=str(body.get("created_by") or ""),
                category=str(body.get("category") or "general"),
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return asset.model_dump(mode="json")

    @router.get("/assets")
    async def list_assets(
        request: Request,
        tenant_id: str = Query(...),
        limit: int = Query(default=100, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
    ) -> dict[str, Any]:
        """处理 GET /assets 请求，查询资产。

        Args:
            request: 当前 HTTP 请求。
            tenant_id: 租户 ID，用于数据隔离。
            limit: 返回记录的最大数量。
            offset: 分页偏移量。

        Returns:
            结构化结果字典。
        """
        await _authorize(request, tenant_id, authenticator, module_access)
        assets = await service.list(tenant_id, limit=limit, offset=offset)
        return {
            "tenant_id": tenant_id,
            "assets": [asset.model_dump(mode="json") for asset in assets],
        }

    @router.get("/assets/{asset_id}")
    async def get_asset(
        request: Request, asset_id: str, tenant_id: str = Query(...)
    ) -> dict[str, Any]:
        """处理 GET /assets/{asset_id} 请求，获取资产。

        Args:
            request: 当前 HTTP 请求。
            asset_id: 资产 ID。
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        await _authorize(request, tenant_id, authenticator, module_access)
        asset = await service.get(tenant_id, asset_id)
        if asset is None:
            raise HTTPException(status_code=404, detail="asset not found")
        return asset.model_dump(mode="json")

    @router.post("/assets/{asset_id}/archive")
    async def archive_asset(
        request: Request,
        asset_id: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        """处理 POST /assets/{asset_id}/archive 请求，提交归档资产。

        Args:
            request: 当前 HTTP 请求。
            asset_id: 资产 ID。
            body: 请求体数据。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        tenant_id = _tenant_id(body)
        await _authorize(request, tenant_id, authenticator, module_access)
        asset = await service.archive(tenant_id, asset_id)
        if asset is None:
            raise HTTPException(status_code=404, detail="asset not found")
        return asset.model_dump(mode="json")

    return router


async def _authorize(
    request: Request,
    tenant_id: str,
    authenticator: AuthenticatorPort,
    module_access: ModuleAccessPort,
) -> None:
    """执行授权决策。

    Args:
        request: 当前 HTTP 请求。
        tenant_id: 租户 ID，用于数据隔离。
        authenticator: 认证器实例。
        module_access: 模块访问。

    Raises:
        HTTPException: 请求参数、状态或依赖不满足要求时抛出。
    """
    authenticator.authorize_tenant(request, tenant_id)
    if not await module_access.is_enabled(tenant_id, "asset"):
        raise HTTPException(status_code=403, detail="Asset module is not enabled for tenant")


def _tenant_id(body: dict[str, Any]) -> str:
    """处理租户ID。

    Args:
        body: 请求体数据。

    Returns:
        字符串结果。

    Raises:
        HTTPException: 请求参数、状态或依赖不满足要求时抛出。
    """
    tenant_id = body.get("tenant_id")
    if not isinstance(tenant_id, str) or not tenant_id.strip():
        raise HTTPException(status_code=422, detail="tenant_id is required")
    return tenant_id.strip()


__all__ = ["create_asset_router"]
