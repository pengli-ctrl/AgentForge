"""模块管理路由模块。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from agentforge.platform.api.security import ApiKeyAuthenticator
from agentforge.platform.application.tenant_module_service import (
    TenantModuleConfigConflict,
    TenantModuleConfigError,
    TenantModuleService,
)


def create_module_admin_router(
    service: TenantModuleService,
    *,
    known_modules: tuple[str, ...] = (),
    authenticator: ApiKeyAuthenticator,
) -> APIRouter:
    """创建模块管理路由。

    Args:
        service: 服务。
        known_modules: 模块。
        authenticator: 认证器实例。

    Returns:
        处理结果对象。
    """
    del known_modules  # 已注册的服务目录是唯一权威来源。
    router = APIRouter(prefix="/v1/admin/tenants/{tenant_id}/modules", tags=["modules"])

    @router.get("")
    async def list_tenant_modules(request: Request, tenant_id: str) -> dict[str, Any]:
        """处理 GET 请求，查询租户模块。

        Args:
            request: 当前 HTTP 请求。
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        authenticator.authorize_admin(request)
        try:
            modules = await service.describe_modules(tenant_id)
        except TenantModuleConfigError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"tenant_id": tenant_id, "modules": modules}

    @router.put("/{module_name}")
    async def set_tenant_module(
        request: Request,
        tenant_id: str,
        module_name: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        """处理 PUT /{module_name} 请求，设置租户模块。

        Args:
            request: 当前 HTTP 请求。
            tenant_id: 租户 ID，用于数据隔离。
            module_name: 模块名称。
            body: 请求体数据。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
            _http_error: 操作无法完成时抛出。
        """
        authenticator.authorize_admin(request)
        enabled = body.get("enabled")
        actor_id = body.get("actor_id")
        if not isinstance(enabled, bool):
            raise HTTPException(status_code=422, detail="enabled must be a boolean")
        if not isinstance(actor_id, str) or not actor_id.strip():
            raise HTTPException(status_code=422, detail="actor_id is required")
        plan_name = body.get("plan_name", "")
        if not isinstance(plan_name, str):
            raise HTTPException(status_code=422, detail="plan_name must be a string")
        try:
            await service.set_enabled(
                tenant_id=tenant_id,
                module_name=module_name,
                enabled=enabled,
                actor_id=actor_id,
                plan_name=plan_name,
            )
            return await service.describe_module(tenant_id, module_name)
        except TenantModuleConfigError as exc:
            raise _http_error(exc) from exc

    @router.get("/{module_name}/config")
    async def get_tenant_module_config(
        request: Request,
        tenant_id: str,
        module_name: str,
    ) -> dict[str, Any]:
        """处理 GET /{module_name}/config 请求，获取租户模块配置。

        Args:
            request: 当前 HTTP 请求。
            tenant_id: 租户 ID，用于数据隔离。
            module_name: 模块名称。

        Returns:
            结构化结果字典。

        Raises:
            _http_error: 操作无法完成时抛出。
        """
        authenticator.authorize_admin(request)
        try:
            return await service.describe_module(tenant_id, module_name)
        except TenantModuleConfigError as exc:
            raise _http_error(exc) from exc

    @router.put("/{module_name}/config")
    async def set_tenant_module_config(
        request: Request,
        tenant_id: str,
        module_name: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        """处理 PUT /{module_name}/config 请求，设置租户模块配置。

        Args:
            request: 当前 HTTP 请求。
            tenant_id: 租户 ID，用于数据隔离。
            module_name: 模块名称。
            body: 请求体数据。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
            _http_error: 操作无法完成时抛出。
        """
        authenticator.authorize_admin(request)
        values = body.get("values")
        actor_id = body.get("actor_id")
        secret_refs = body.get("secret_refs", {})
        expected_version = body.get("expected_version")
        enabled = body.get("enabled")
        if not isinstance(values, dict):
            raise HTTPException(status_code=422, detail="values must be an object")
        if not isinstance(actor_id, str) or not actor_id.strip():
            raise HTTPException(status_code=422, detail="actor_id is required")
        if not isinstance(secret_refs, dict) or not all(
            isinstance(key, str) and isinstance(value, str) for key, value in secret_refs.items()
        ):
            raise HTTPException(status_code=422, detail="secret_refs must map names to references")
        if expected_version is not None and (
            not isinstance(expected_version, int) or expected_version < 1
        ):
            raise HTTPException(
                status_code=422,
                detail="expected_version must be a positive integer",
            )
        if enabled is not None and not isinstance(enabled, bool):
            raise HTTPException(status_code=422, detail="enabled must be a boolean")
        try:
            await service.set_config(
                tenant_id=tenant_id,
                module_name=module_name,
                values=values,
                actor_id=actor_id,
                secret_refs=secret_refs,
                expected_version=expected_version,
                enabled=enabled,
            )
            return await service.describe_module(tenant_id, module_name)
        except TenantModuleConfigError as exc:
            raise _http_error(exc) from exc

    return router


def _http_error(exc: TenantModuleConfigError) -> HTTPException:
    """处理HTTP错误。

    Args:
        exc: 输入参数。

    Returns:
        处理结果对象。
    """
    if isinstance(exc, TenantModuleConfigConflict):
        return HTTPException(status_code=409, detail=str(exc))
    if "not deployed" in str(exc):
        return HTTPException(status_code=404, detail=str(exc))
    return HTTPException(status_code=422, detail=str(exc))
