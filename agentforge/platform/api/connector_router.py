"""AgentForge 平台 API 层：connector_router。

本模块定义 connector_ 相关 HTTP 接口，负责请求解析、鉴权校验、调用应用服务并组织响应。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要函数：create_connector_router。
"""

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
    """创建新的业务对象，并返回调用方需要的结果。

    Args:
        registry: ConnectorRegistry，调用方传入的 registry 参数。
        repository: Any | None，调用方传入的 repository 参数。
        adapter_factory: Any | None，调用方传入的 adapter_factory 参数。
        authenticator: ApiKeyAuthenticator | None，调用方传入的 authenticator 参数。

    Returns:
        APIRouter，函数执行后的结果。

    Raises:
        HTTPException: 当输入、状态或外部依赖不满足要求时抛出。
    """
    router = APIRouter(prefix="/v1/connectors", tags=["connectors"])

    @router.get("")
    async def list_connectors(request: Request, tenant_id: str | None = None) -> dict:
        """查询并返回列表结果，并返回调用方需要的结果。

        Args:
            request: Request，调用方传入的 request 参数。
            tenant_id: str | None，调用方传入的 tenant_id 参数。

        Returns:
            dict，函数执行后的结果。
        """
        _authorize_admin(authenticator, request)
        specs = registry.list_specs(tenant_id)
        return {"connectors": [spec_to_public_dict(s) for s in specs]}

    @router.post("")
    async def register_connector(request: Request, spec: ConnectorSpec) -> dict:
        """执行 register_connector 对应的逻辑，并返回处理结果。

        Args:
            request: Request，调用方传入的 request 参数。
            spec: ConnectorSpec，调用方传入的 spec 参数。

        Returns:
            dict，函数执行后的结果。
        """
        _authorize_admin(authenticator, request)
        adapter = _build_adapter(adapter_factory, spec)
        registry.register(spec, adapter)
        if repository is not None:
            await repository.save_spec(spec)
        return spec_to_public_dict(spec)

    @router.delete("/{connector_id}")
    async def delete_connector(request: Request, connector_id: str) -> dict:
        """删除指定数据，并返回调用方需要的结果。

        Args:
            request: Request，调用方传入的 request 参数。
            connector_id: str，调用方传入的 connector_id 参数。

        Returns:
            dict，函数执行后的结果。
        """
        _authorize_admin(authenticator, request)
        if repository is not None:
            await repository.delete_spec(connector_id)
        return {"deleted": connector_id}

    @router.get("/{connector_id}")
    async def get_connector(request: Request, connector_id: str) -> dict:
        """读取并返回指定数据，并返回调用方需要的结果。

        Args:
            request: Request，调用方传入的 request 参数。
            connector_id: str，调用方传入的 connector_id 参数。

        Returns:
            dict，函数执行后的结果。

        Raises:
            HTTPException: 当输入、状态或外部依赖不满足要求时抛出。
        """
        _authorize_admin(authenticator, request)
        spec = registry.get_spec(connector_id)
        if spec is None:
            raise HTTPException(status_code=404, detail="connector not found")
        return spec_to_public_dict(spec)

    @router.get("/{connector_id}/health")
    async def connector_health(request: Request, connector_id: str) -> dict:
        """执行 connector_health 对应的逻辑，并返回处理结果。

        Args:
            request: Request，调用方传入的 request 参数。
            connector_id: str，调用方传入的 connector_id 参数。

        Returns:
            dict，函数执行后的结果。

        Raises:
            HTTPException: 当输入、状态或外部依赖不满足要求时抛出。
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
        # 说明：该步骤用于保证业务流程、租户隔离和可追踪性。
        # 验证租户上下文和隔离约束。
        """执行 invoke_connector 对应的逻辑，并返回处理结果。

        Args:
            request: Request，调用方传入的 request 参数。
            connector_id: str，调用方传入的 connector_id 参数。
            action: str，调用方传入的 action 参数。
            tenant_id: str，调用方传入的 tenant_id 参数。
            payload: dict[str, Any] | None，调用方传入的 payload 参数。
            idempotency_key: str，调用方传入的 idempotency_key 参数。
            task_id: str，调用方传入的 task_id 参数。
            trace_id: str，调用方传入的 trace_id 参数。

        Returns:
            dict，函数执行后的结果。

        Raises:
            HTTPException: 当输入、状态或外部依赖不满足要求时抛出。
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
    # 说明：该步骤用于保证业务流程、租户隔离和可追踪性。
    # 验证管理员权限和边界行为。
    """执行 _authorize_admin 对应的逻辑，并返回处理结果。

    Args:
        auth: ApiKeyAuthenticator | None，调用方传入的 auth 参数。
        request: Request，调用方传入的 request 参数。

    Returns:
        None，函数执行后的结果。
    """
    if auth is None:
        return
    auth.authorize_admin(request)


def _authorize_tenant(
    auth: ApiKeyAuthenticator | None,
    request: Request,
    tenant_id: str | None,
) -> None:
    """执行 _authorize_tenant 对应的逻辑，并返回处理结果。

    Args:
        auth: ApiKeyAuthenticator | None，调用方传入的 auth 参数。
        request: Request，调用方传入的 request 参数。
        tenant_id: str | None，调用方传入的 tenant_id 参数。

    Returns:
        None，函数执行后的结果。
    """
    if auth is None:
        return
    auth.authorize_tenant(request, tenant_id)


def _build_adapter(adapter_factory: Any, spec: ConnectorSpec) -> Connector:
    """执行 _build_adapter 对应的逻辑，并返回处理结果。

    Args:
        adapter_factory: Any，调用方传入的 adapter_factory 参数。
        spec: ConnectorSpec，调用方传入的 spec 参数。

    Returns:
        Connector，函数执行后的结果。

    Raises:
        HTTPException: 当输入、状态或外部依赖不满足要求时抛出。
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
