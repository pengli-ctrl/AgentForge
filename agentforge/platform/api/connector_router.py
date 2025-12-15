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
    router = APIRouter(prefix="/v1/connectors", tags=["connectors"])

    @router.get("")
    async def list_connectors(request: Request, tenant_id: str | None = None) -> dict:
        _authorize_admin(authenticator, request)
        specs = registry.list_specs(tenant_id)
        return {"connectors": [spec_to_public_dict(s) for s in specs]}

    @router.post("")
    async def register_connector(request: Request, spec: ConnectorSpec) -> dict:
        _authorize_admin(authenticator, request)
        adapter = _build_adapter(adapter_factory, spec)
        registry.register(spec, adapter)
        if repository is not None:
            await repository.save_spec(spec)
        return spec_to_public_dict(spec)

    @router.delete("/{connector_id}")
    async def delete_connector(request: Request, connector_id: str) -> dict:
        _authorize_admin(authenticator, request)
        if repository is not None:
            await repository.delete_spec(connector_id)
        return {"deleted": connector_id}

    @router.get("/{connector_id}")
    async def get_connector(request: Request, connector_id: str) -> dict:
        _authorize_admin(authenticator, request)
        spec = registry.get_spec(connector_id)
        if spec is None:
            raise HTTPException(status_code=404, detail="connector not found")
        return spec_to_public_dict(spec)

    @router.get("/{connector_id}/health")
    async def connector_health(request: Request, connector_id: str) -> dict:
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
        # Any authorized principal may invoke, but must be bound to the tenant
        # the request scopes itself to (cross-tenant invocation is refused).
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
    # No authenticator wired (or auth disabled) => management endpoints stay
    # reachable in a trusted/dev environment; in protected deployments the
    # authenticator enforces the admin API key.
    if auth is None:
        return
    auth.authorize_admin(request)


def _authorize_tenant(
    auth: ApiKeyAuthenticator | None,
    request: Request,
    tenant_id: str | None,
) -> None:
    if auth is None:
        return
    auth.authorize_tenant(request, tenant_id)


def _build_adapter(adapter_factory: Any, spec: ConnectorSpec) -> Connector:
    if adapter_factory is not None:
        adapter = adapter_factory(spec)
        if isinstance(adapter, Connector):
            return adapter
        raise HTTPException(
            status_code=500,
            detail="adapter factory did not produce a Connector",
        )
    raise HTTPException(status_code=500, detail="no adapter factory configured")
