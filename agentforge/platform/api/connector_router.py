from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from agentforge.platform.application.connector_registry import Connector, ConnectorRegistry
from agentforge.platform.domain.connector import ConnectorContext, ConnectorSpec


def create_connector_router(
    registry: ConnectorRegistry,
    repository: Any | None = None,
    adapter_factory: Any | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/v1/connectors", tags=["connectors"])

    @router.get("")
    async def list_connectors(tenant_id: str | None = None) -> dict:
        specs = registry.list_specs(tenant_id)
        return {"connectors": [s.model_dump(mode="json") for s in specs]}

    @router.post("")
    async def register_connector(spec: ConnectorSpec) -> dict:
        adapter = _build_adapter(adapter_factory, spec)
        registry.register(spec, adapter)
        if repository is not None:
            await repository.save_spec(spec)
        return spec.model_dump(mode="json")

    @router.delete("/{connector_id}")
    async def delete_connector(connector_id: str) -> dict:
        if repository is not None:
            await repository.delete_spec(connector_id)
        return {"deleted": connector_id}

    @router.get("/{connector_id}")
    async def get_connector(connector_id: str) -> dict:
        spec = registry.get_spec(connector_id)
        if spec is None:
            raise HTTPException(status_code=404, detail="connector not found")
        return spec.model_dump(mode="json")

    @router.get("/{connector_id}/health")
    async def connector_health(connector_id: str) -> dict:
        health = await registry.health(connector_id)
        if health is None:
            raise HTTPException(status_code=404, detail="connector not found")
        return health.model_dump(mode="json")

    @router.post("/{connector_id}/invoke")
    async def invoke_connector(
        connector_id: str,
        action: str,
        tenant_id: str,
        payload: dict[str, Any] | None = None,
        idempotency_key: str = "",
        task_id: str = "",
        trace_id: str = "",
    ) -> dict:
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
