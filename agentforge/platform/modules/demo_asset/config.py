"""配置模块。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class AssetModuleConfig(BaseModel):
    """资产模块配置模型。

    Attributes:
        retention_days: 保留。
        allow_manual_archive: 允许归档。
    """

    model_config = ConfigDict(extra="forbid")

    retention_days: int = Field(default=365, ge=1)
    allow_manual_archive: bool = True


def default_asset_config() -> AssetModuleConfig:
    """创建默认资产配置。

    Returns:
        资产模块配置结果。
    """
    return AssetModuleConfig()


__all__ = ["AssetModuleConfig", "default_asset_config"]
