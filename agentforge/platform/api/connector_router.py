"""连接器路由模块。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from agentforge.platform.api.security import ApiKeyAuthenticator
from agentforge.platform.application.connector_registry import Connector, ConnectorRegistry
from agentforge.platform.domain.connector import (
    ConnectorContext,
    ConnectorSpec,
    spec_to_public_dict,
)


def create_connector_router(
    registry: ConnectorRegistry,
    repository: Any | None = None,
    adapter_factory: Any | None = None,
    authenticator: ApiKeyAuthenticator | None = None,
) -> APIRouter:
    """创建连接器路由。

    Args:
        registry: 注册表实例。
        repository: 数据仓储实现。
        adapter_factory: 适配器工厂。
        authenticator: 认证器实例。

    Returns:
        处理结果对象。
    """
    router = APIRouter(prefix="/v1/connectors", tags=["connectors"])

    @router.get("")
    async def list_connectors(request: Request, tenant_id: str | None = None) -> dict:
        """处理 GET 请求，查询连接器。

        Args:
            request: 当前 HTTP 请求。
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            结构化结果字典。
        """
        _authorize_admin(authenticator, request)
        specs = registry.list_specs(tenant_id)
        return {"connectors": [spec_to_public_dict(s) for s in specs]}

    @router.post("")
    async def register_connector(request: Request, spec: ConnectorSpec) -> dict:
        """处理 POST 请求，注册连接器。

        Args:
            request: 当前 HTTP 请求。
            spec: 资源规格定义。

        Returns:
            结构化结果字典。
        """
        _authorize_admin(authenticator, request)
        adapter = _build_adapter(adapter_factory, spec)
        registry.register(spec, adapter)
        if repository is not None:
            await repository.save_spec(spec)
        return spec_to_public_dict(spec)

    @router.delete("/{connector_id}")
    async def delete_connector(request: Request, connector_id: str) -> dict:
        """处理 DELETE /{connector_id} 请求，删除连接器。

        Args:
            request: 当前 HTTP 请求。
            connector_id: 连接器 ID。

        Returns:
            结构化结果字典。
        """
        _authorize_admin(authenticator, request)
        if repository is not None:
            await repository.delete_spec(connector_id)
        return {"deleted": connector_id}

    @router.get("/{connector_id}")
    async def get_connector(request: Request, connector_id: str) -> dict:
        """处理 GET /{connector_id} 请求，获取连接器。

        Args:
            request: 当前 HTTP 请求。
            connector_id: 连接器 ID。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        _authorize_admin(authenticator, request)
        spec = registry.get_spec(connector_id)
        if spec is None:
            raise HTTPException(status_code=404, detail="connector not found")
        return spec_to_public_dict(spec)

    @router.get("/{connector_id}/health")
    async def connector_health(request: Request, connector_id: str) -> dict:
        """检查连接器健康状态。

        Args:
            request: 当前 HTTP 请求。
            connector_id: 连接器 ID。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        _authorize_admin(authenticator, request)
        health = await registry.health(connector_id)
        if health is None:
            raise HTTPException(status_code=404, detail="connector not found")
        return health.model_dump(mode="json")

    @router.post("/{connector_id}/invoke")
    async def invoke_connector(
        request: Request,
        connector_id: str,
        action: str,
        tenant_id: str,
        payload: dict[str, Any] | None = None,
        idempotency_key: str = "",
        task_id: str = "",
        trace_id: str = "",
    ) -> dict:
        # 验证租户上下文和隔离约束。
        """处理 POST /{connector_id}/invoke 请求，调用连接器。

        Args:
            request: 当前 HTTP 请求。
            connector_id: 连接器 ID。
            action: 待执行动作名称。
            tenant_id: 租户 ID，用于数据隔离。
            payload: 事件、工作流或请求载荷。
            idempotency_key: 幂等键，用于避免重复处理。
            task_id: 任务 ID。
            trace_id: 链路追踪 ID。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        _authorize_tenant(authenticator, request, tenant_id)
        result = await registry.invoke(
            connector_id,
            action,
            payload or {},
            ConnectorContext(
                tenant_id=tenant_id,
                idempotency_key=idempotency_key,
                task_id=task_id,
                trace_id=trace_id,
            ),
        )
        if result.ok:
            return result.model_dump(mode="json")
        if result.error in {"connector not registered", "adapter not bound"}:
            raise HTTPException(status_code=404, detail=result.error)
        raise HTTPException(
            status_code=502,
            detail={"error": result.error, "action": result.action},
        )

    return router


def _authorize_admin(auth: ApiKeyAuthenticator | None, request: Request) -> None:
    # 验证禁用状态下策略和功能不会意外生效。
    # 验证管理员权限和边界行为。
    """授权管理。

    Args:
        auth: 鉴权。
        request: 当前 HTTP 请求。
    """
    if auth is None:
        return
    auth.authorize_admin(request)


def _authorize_tenant(
    auth: ApiKeyAuthenticator | None,
    request: Request,
    tenant_id: str | None,
) -> None:
    """授权租户。

    Args:
        auth: 鉴权。
        request: 当前 HTTP 请求。
        tenant_id: 租户 ID，用于数据隔离。
    """
    if auth is None:
        return
    auth.authorize_tenant(request, tenant_id)


def _build_adapter(adapter_factory: Any, spec: ConnectorSpec) -> Connector:
    """构建适配器。

    Args:
        adapter_factory: 适配器工厂。
        spec: 资源规格定义。

    Returns:
        连接器结果。

    Raises:
        HTTPException: 请求参数、状态或依赖不满足要求时抛出。
    """
    if adapter_factory is not None:
        adapter = adapter_factory(spec)
        if isinstance(adapter, Connector):
            return adapter
        raise HTTPException(
            status_code=500,
            detail="adapter factory did not produce a Connector",
        )
    raise HTTPException(status_code=500, detail="no adapter factory configured")
