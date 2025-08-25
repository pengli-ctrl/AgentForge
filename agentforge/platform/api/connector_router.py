from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from agentforge.platform.application.connector_registry import ConnectorRegistry
from agentforge.platform.domain.connector import ConnectorContext


def create_connector_router(
    registry: ConnectorRegistry,
) -> APIRouter:
    router = APIRouter(prefix="/v1/connectors", tags=["connectors"])

    @router.get("")
    async def list_connectors(tenant_id: str | None = None) -> dict:
        specs = registry.list_specs(tenant_id)
        return {"connectors": [s.model_dump(mode="json") for s in specs]}

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
