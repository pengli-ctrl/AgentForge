"""AgentForge 平台基础设施层：memory_connector_repository。

本模块提供 memory_connector_repository 的内存实现，用于单元测试、本地开发和离线验证。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：MemoryConnectorRepository。
"""

from __future__ import annotations

from agentforge.platform.domain.connector import ConnectorSpec


class MemoryConnectorRepository:
    """MemoryConnectorRepository。

    MemoryConnectorRepository 负责数据读写，并确保租户隔离、事务一致性和持久化细节不泄漏到应用层。

    主要成员：
    - 方法 save_spec()。
    - 方法 get_spec()。
    - 方法 list_specs()。
    - 方法 delete_spec()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    def __init__(self) -> None:
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Returns:
            None，函数执行后的结果。
        """
        self._specs: dict[str, ConnectorSpec] = {}

    async def save_spec(self, spec: ConnectorSpec) -> None:
        """保存业务数据，并返回调用方需要的结果。

        Args:
            spec: ConnectorSpec，调用方传入的 spec 参数。

        Returns:
            None，函数执行后的结果。
        """
        self._specs[spec.connector_id] = spec

    async def get_spec(self, connector_id: str) -> ConnectorSpec | None:
        """读取并返回指定数据，并返回调用方需要的结果。

        Args:
            connector_id: str，调用方传入的 connector_id 参数。

        Returns:
            ConnectorSpec | None，函数执行后的结果。
        """
        return self._specs.get(connector_id)

    async def list_specs(
        self,
        tenant_id: str | None = None,
        limit: int = 100,
    ) -> list[ConnectorSpec]:
        """查询并返回列表结果，并返回调用方需要的结果。

        Args:
            tenant_id: str | None，调用方传入的 tenant_id 参数。
            limit: int，调用方传入的 limit 参数。

        Returns:
            list[ConnectorSpec]，函数执行后的结果。
        """
        specs = list(self._specs.values())
        if tenant_id is not None:
            specs = [s for s in specs if s.tenant_id == tenant_id]
        specs.sort(key=lambda s: s.created_at)
        return specs[:limit]

    async def delete_spec(self, connector_id: str) -> None:
        """删除指定数据，并返回调用方需要的结果。

        Args:
            connector_id: str，调用方传入的 connector_id 参数。

        Returns:
            None，函数执行后的结果。
        """
        self._specs.pop(connector_id, None)
