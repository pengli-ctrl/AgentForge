"""记忆租户账户仓储模块。"""

from __future__ import annotations

from copy import deepcopy

from agentforge.platform.domain.tenant_account import TenantAccount


class MemoryTenantAccountRepository:
    """租户账户仓储，负责持久化读写。"""

    def __init__(self) -> None:
        """初始化 MemoryTenantAccountRepository。"""
        self._accounts: dict[str, TenantAccount] = {}

    async def save(self, account: TenantAccount) -> None:
        """保存租户账户。

        Args:
            account: 租户账户。
        """
        self._accounts[account.tenant_id] = deepcopy(account)

    async def get(self, tenant_id: str) -> TenantAccount | None:
        """读取租户账户。

        Args:
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            租户无结果。
        """
        account = self._accounts.get(tenant_id)
        return deepcopy(account) if account is not None else None

    async def list(self, limit: int = 100) -> list[TenantAccount]:
        """查询租户账户。

        Args:
            limit: 返回记录的最大数量。

        Returns:
            结果列表。
        """
        accounts = sorted(self._accounts.values(), key=lambda item: item.created_at, reverse=True)
        return [deepcopy(account) for account in accounts[:limit]]


__all__ = ["MemoryTenantAccountRepository"]
