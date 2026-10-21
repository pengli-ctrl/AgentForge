"""记忆连接器仓储模块。"""

from __future__ import annotations

from agentforge.platform.domain.connector import ConnectorSpec


class MemoryConnectorRepository:
    """记忆连接器仓储，负责持久化读写。"""

    def __init__(self) -> None:
        """初始化 MemoryConnectorRepository。"""
        self._specs: dict[str, ConnectorSpec] = {}

    async def save_spec(self, spec: ConnectorSpec) -> None:
        """保存规格。

        Args:
            spec: 资源规格定义。
        """
        self._specs[spec.connector_id] = spec

    async def get_spec(self, connector_id: str) -> ConnectorSpec | None:
        """获取规格。

        Args:
            connector_id: 连接器 ID。

        Returns:
            连接器规格无结果。
        """
        return self._specs.get(connector_id)

    async def list_specs(
        self,
        tenant_id: str | None = None,
        limit: int = 100,
    ) -> list[ConnectorSpec]:
        """查询规格。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            limit: 返回记录的最大数量。

        Returns:
            结果列表。
        """
        specs = list(self._specs.values())
        if tenant_id is not None:
            specs = [s for s in specs if s.tenant_id == tenant_id]
        specs.sort(key=lambda s: s.created_at)
        return specs[:limit]

    async def delete_spec(self, connector_id: str) -> None:
        """删除规格。

        Args:
            connector_id: 连接器 ID。
        """
        self._specs.pop(connector_id, None)
