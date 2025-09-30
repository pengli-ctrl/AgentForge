from __future__ import annotations

from agentforge.platform.domain.tenant_quota import TenantQuota


class MemoryTenantQuotaRepository:
    """In-memory per-tenant quota repository."""

    def __init__(self) -> None:
        self._quotas: dict[str, TenantQuota] = {}

    async def upsert(self, quota: TenantQuota) -> None:
        self._quotas[quota.tenant_id] = quota

    async def get(self, tenant_id: str) -> TenantQuota | None:
        return self._quotas.get(tenant_id)

    async def list(self, limit: int = 100) -> list[TenantQuota]:
        return list(self._quotas.values())[:limit]

    async def delete(self, tenant_id: str) -> None:
        self._quotas.pop(tenant_id, None)
