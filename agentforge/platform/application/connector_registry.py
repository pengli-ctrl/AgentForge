from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

from agentforge.platform.domain.connector import (
    ConnectorContext,
    ConnectorHealth,
    ConnectorInvocationResult,
    ConnectorSpec,
)

__all__ = ["Connector", "ConnectorRegistry"]


class Connector(ABC):
    """Connector SDK contract (aligned with engineering spec 5.11 / 6.10).

    A Connector is a named, versioned adapter to an external system. Every
    invocation carries a ConnectorContext that includes idempotency/trace and
    tenant scoping. Write-like actions are expected to be compensatable so a
    higher-level workflow can roll back a partial published action.
    """

    name: str
    version: str = "1.0"
    risk_level: str = "low"

    @abstractmethod
    async def health(self) -> ConnectorHealth:
        raise NotImplementedError

    @abstractmethod
    async def invoke(
        self,
        action: str,
        payload: dict,
        context: ConnectorContext,
    ) -> ConnectorInvocationResult:
        raise NotImplementedError

    @abstractmethod
    async def compensate(
        self,
        action: str,
        payload: dict,
        context: ConnectorContext,
    ) -> ConnectorInvocationResult:
        raise NotImplementedError


class ConnectorRegistry:
    """In-memory registration of connector SDK adapters.

    Mirrors PromptRegistry style: process-memory registry, no DB table in this
    increment. A durable connector table is deferred to stage C/D connector
    management. Supports registration, lookup by (spec, adapter) map keyed by
    connector_id, plus health aggregation.
    """

    def __init__(self) -> None:
        self._specs: dict[str, ConnectorSpec] = {}
        self._adapters: dict[str, Connector] = {}

    def register(self, spec: ConnectorSpec, adapter: Connector) -> ConnectorSpec:
        if adapter.name != spec.name:
            raise ValueError(
                f"Adapter name {adapter.name!r} does not match spec name {spec.name!r}"
            )
        self._specs[spec.connector_id] = spec
        self._adapters[spec.connector_id] = adapter
        return spec

    def get_spec(self, connector_id: str) -> ConnectorSpec | None:
        return self._specs.get(connector_id)

    def list_specs(self, tenant_id: str | None = None) -> list[ConnectorSpec]:
        if tenant_id is None:
            return list(self._specs.values())
        return [s for s in self._specs.values() if s.tenant_id == tenant_id]

    def get_adapter(self, connector_id: str) -> Connector | None:
        return self._adapters.get(connector_id)

    def set_adapter(self, connector_id: str, adapter: Connector) -> None:
        """Bind (or rebind) an adapter to an already-registered spec's id."""
        self._adapters[connector_id] = adapter

    async def load_from_repository(
        self,
        repository: Any,
        adapter_factory: Callable[[ConnectorSpec], Connector] | None = None,
    ) -> int:
        """Load persisted specs into the registry and rebind adapters.

        repository must implement list_specs(). adapters are created lazily by
        adapter_factory when provided; otherwise specs are stored without an
        adapter (adapter can be bound later via set_adapter). Returns the number
        of specs loaded.
        """
        loaded = 0
        for spec in await repository.list_specs():
            self._specs[spec.connector_id] = spec
            if adapter_factory is not None:
                self._adapters[spec.connector_id] = adapter_factory(spec)
            loaded += 1
        return loaded

    async def health(self, connector_id: str) -> ConnectorHealth | None:
        adapter = self._adapters.get(connector_id)
        if adapter is None:
            return None
        return await adapter.health()

    async def list_health(self, tenant_id: str | None = None) -> list[ConnectorHealth]:
        specs = self.list_specs(tenant_id)
        results: list[ConnectorHealth] = []
        for spec in specs:
            adapter = self._adapters.get(spec.connector_id)
            if adapter is None:
                results.append(
                    ConnectorHealth(
                        connector_id=spec.connector_id,
                        healthy=False,
                        detail="adapter not bound",
                    )
                )
                continue
            results.append(await adapter.health())
        return results

    async def invoke(
        self,
        connector_id: str,
        action: str,
        payload: dict,
        context: ConnectorContext,
    ) -> ConnectorInvocationResult:
        spec = self._specs.get(connector_id)
        if spec is None:
            return ConnectorInvocationResult(
                connector_id=connector_id,
                action=action,
                ok=False,
                error="connector not registered",
            )
        if not spec.enabled:
            return ConnectorInvocationResult(
                connector_id=connector_id,
                action=action,
                ok=False,
                error="connector disabled",
            )
        if spec.allowed_actions and action not in spec.allowed_actions:
            return ConnectorInvocationResult(
                connector_id=connector_id,
                action=action,
                ok=False,
                error=f"action not allowed: {action}",
            )
        if context.tenant_id != spec.tenant_id:
            return ConnectorInvocationResult(
                connector_id=connector_id,
                action=action,
                ok=False,
                error="tenant mismatch",
            )
        adapter = self._adapters.get(connector_id)
        if adapter is None:
            return ConnectorInvocationResult(
                connector_id=connector_id,
                action=action,
                ok=False,
                error="adapter not bound",
            )
        return await adapter.invoke(action, payload, context)
