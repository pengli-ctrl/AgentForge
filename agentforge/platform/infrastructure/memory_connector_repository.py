from __future__ import annotations

from agentforge.platform.domain.connector import ConnectorSpec


class MemoryConnectorRepository:
    """In-memory connector spec repository for unit tests (no DB needed)."""

    def __init__(self) -> None:
        self._specs: dict[str, ConnectorSpec] = {}

    async def save_spec(self, spec: ConnectorSpec) -> None:
        self._specs[spec.connector_id] = spec

    async def get_spec(self, connector_id: str) -> ConnectorSpec | None:
        return self._specs.get(connector_id)

    async def list_specs(
        self,
        tenant_id: str | None = None,
        limit: int = 100,
    ) -> list[ConnectorSpec]:
        specs = list(self._specs.values())
        if tenant_id is not None:
            specs = [s for s in specs if s.tenant_id == tenant_id]
        specs.sort(key=lambda s: s.created_at)
        return specs[:limit]

    async def delete_spec(self, connector_id: str) -> None:
        self._specs.pop(connector_id, None)
