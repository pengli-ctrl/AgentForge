"""端口模块。"""

from __future__ import annotations

from typing import Protocol

from agentforge.platform.modules.demo_asset.domain.asset import Asset


class AssetRepository(Protocol):
    """资产仓储，负责持久化读写。"""

    async def save(self, asset: Asset) -> None:
        """保存资产。

        Args:
            asset: 资产。
        """
        ...

    async def get(self, tenant_id: str, asset_id: str) -> Asset | None:
        """读取资产。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            asset_id: 资产 ID。

        Returns:
            资产无结果。
        """
        ...

    async def list(self, tenant_id: str, *, limit: int = 100, offset: int = 0) -> list[Asset]:
        """查询资产。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            limit: 返回记录的最大数量。
            offset: 分页偏移量。

        Returns:
            结果列表。
        """
        ...


__all__ = ["AssetRepository"]
