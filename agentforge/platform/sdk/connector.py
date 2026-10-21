"""连接器模块。"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel

from agentforge.platform.domain.connector import ConnectorKind, ConnectorRiskLevel


@dataclass(frozen=True)
class ConnectorRegistration:
    """租户无关的连接器注册声明。

    Attributes:
        connector_id: 连接器ID。
        name: 名称。
        kind: 资源种类。
        version: 版本号。
        risk_level: 风险级别。
        endpoint: 端点。
        allowed_actions: 允许操作。
        config_schema: 配置结构。
    """

    connector_id: str
    name: str
    kind: ConnectorKind
    version: str = "1.0"
    risk_level: ConnectorRiskLevel = ConnectorRiskLevel.LOW
    endpoint: str | None = None
    allowed_actions: tuple[str, ...] = ()
    config_schema: type[BaseModel] | None = None
