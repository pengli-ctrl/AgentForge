"""记忆仓储模块。"""

from __future__ import annotations

from copy import deepcopy

from agentforge.platform.modules.demo_asset.domain.asset import Asset


class MemoryAssetRepository:
    """资产仓储，负责持久化读写。"""

    def __init__(self) -> None:
        """初始化 MemoryAssetRepository。"""
        self._assets: dict[tuple[str, str], Asset] = {}

    async def save(self, asset: Asset) -> None:
        """保存资产。

        Args:
            asset: 资产。
        """
        self._assets[(asset.tenant_id, asset.asset_id)] = deepcopy(asset)

    async def get(self, tenant_id: str, asset_id: str) -> Asset | None:
        """读取资产。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            asset_id: 资产 ID。

        Returns:
            资产无结果。
        """
        asset = self._assets.get((tenant_id, asset_id))
        return deepcopy(asset) if asset is not None else None

    async def list(self, tenant_id: str, *, limit: int = 100, offset: int = 0) -> list[Asset]:
        """查询资产。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            limit: 返回记录的最大数量。
            offset: 分页偏移量。

        Returns:
            结果列表。
        """
        assets = [
            asset for (owner_tenant, _), asset in self._assets.items() if owner_tenant == tenant_id
        ]
        assets.sort(key=lambda item: item.created_at, reverse=True)
        return [deepcopy(asset) for asset in assets[offset : offset + limit]]


__all__ = ["MemoryAssetRepository"]
