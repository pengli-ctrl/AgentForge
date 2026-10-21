"""记忆租户配额仓储模块。"""

from __future__ import annotations

from agentforge.platform.domain.tenant_quota import TenantQuota


class MemoryTenantQuotaRepository:
    """租户配额仓储，负责持久化读写。"""

    def __init__(self) -> None:
        """初始化 MemoryTenantQuotaRepository。"""
        self._quotas: dict[str, TenantQuota] = {}

    async def upsert(self, quota: TenantQuota) -> None:
        """新建或更新租户配额。

        Args:
            quota: 配额配置。
        """
        self._quotas[quota.tenant_id] = quota

    async def get(self, tenant_id: str) -> TenantQuota | None:
        """读取租户配额。

        Args:
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            租户配额无结果。
        """
        return self._quotas.get(tenant_id)

    async def list(self, limit: int = 100) -> list[TenantQuota]:
        """查询租户配额。

        Args:
            limit: 返回记录的最大数量。

        Returns:
            结果列表。
        """
        return list(self._quotas.values())[:limit]

    async def delete(self, tenant_id: str) -> None:
        """删除租户配额。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
        """
        self._quotas.pop(tenant_id, None)
