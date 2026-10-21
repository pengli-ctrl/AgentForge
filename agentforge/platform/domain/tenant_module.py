"""租户模块。"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ConfigSource = Literal["deployment_default", "tenant_override"]

_SECRET_REFERENCE_PATTERN = re.compile(r"^(?:vault|kms|secret|env)://[A-Za-z0-9._/-]+$")


class TenantModuleConfig(BaseModel):
    """租户模块配置模型。

    Attributes:
        tenant_id: 租户 ID，用于数据隔离。
        module_name: 模块名称。
        enabled: 是否启用。
        config_version: 配置版本。
        source: 调用或事件来源。
        updated_by: 由。
        plan_name: 套餐名称。
        updated_at: 更新时间。
        values: 值。
        secret_refs: 密钥。
    """

    model_config = ConfigDict(extra="forbid")

    tenant_id: str
    module_name: str
    enabled: bool = True
    config_version: int = Field(default=1, ge=1)
    source: ConfigSource = "tenant_override"
    updated_by: str = ""
    # 为兼容最初仅支持启用状态的 API 结构而保留。
    plan_name: str = ""
    updated_at: datetime | None = None
    values: dict[str, Any] = Field(default_factory=dict)
    secret_refs: dict[str, str] = Field(default_factory=dict)

    @field_validator("tenant_id", "module_name", "updated_by")
    @classmethod
    def _strip_identifiers(cls, value: str) -> str:
        """处理去除。

        Args:
            value: 待处理值。

        Returns:
            字符串结果。
        """
        return value.strip()

    @field_validator("secret_refs")
    @classmethod
    def _validate_secret_references(cls, value: dict[str, str]) -> dict[str, str]:
        """校验密钥。

        Args:
            value: 待处理值。

        Returns:
            结构化结果字典。

        Raises:
            ValueError: 输入值或业务状态不合法时抛出。
        """
        normalized: dict[str, str] = {}
        for name, reference in value.items():
            key = name.strip()
            if not key or not key.replace("_", "").isalnum():
                raise ValueError("secret reference names must be alphanumeric identifiers")
            if not _SECRET_REFERENCE_PATTERN.fullmatch(reference):
                raise ValueError(
                    f"secret reference {key!r} must use vault://, kms://, secret:// or env://"
                )
            normalized[key] = reference
        return normalized


# 为配置能力引入前的集成提供向后兼容导入。
TenantModuleState = TenantModuleConfig

__all__ = ["ConfigSource", "TenantModuleConfig", "TenantModuleState"]
