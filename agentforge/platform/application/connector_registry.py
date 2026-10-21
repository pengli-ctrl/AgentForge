"""连接器注册表模块。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

from agentforge.platform.domain.connector import (
    ConnectorContext,
    ConnectorHealth,
    ConnectorInvocationResult,
    ConnectorSpec,
)

__all__ = ["Connector", "ConnectorRegistry"]


class Connector(ABC):
    """连接器抽象基类，定义扩展点和通用生命周期。

    Attributes:
        name: 名称。
        version: 版本号。
        risk_level: 风险级别。
    """

    name: str
    version: str = "1.0"
    risk_level: str = "low"

    @abstractmethod
    async def health(self) -> ConnectorHealth:
        """检查连接器健康状态。

        Raises:
            NotImplementedError: 操作无法完成时抛出。

        Returns:
            连接器健康结果。
        """
        raise NotImplementedError

    @abstractmethod
    async def invoke(
        self,
        action: str,
        payload: dict,
        context: ConnectorContext,
    ) -> ConnectorInvocationResult:
        """调用连接器。

        Args:
            action: 待执行动作名称。
            payload: 事件、工作流或请求载荷。
            context: 执行上下文。

        Raises:
            NotImplementedError: 操作无法完成时抛出。

        Returns:
            连接器结果结果。
        """
        raise NotImplementedError

    @abstractmethod
    async def compensate(
        self,
        action: str,
        payload: dict,
        context: ConnectorContext,
    ) -> ConnectorInvocationResult:
        """补偿连接器。

        Args:
            action: 待执行动作名称。
            payload: 事件、工作流或请求载荷。
            context: 执行上下文。

        Raises:
            NotImplementedError: 操作无法完成时抛出。

        Returns:
            连接器结果结果。
        """
        raise NotImplementedError


class ConnectorRegistry:
    """连接器注册表。"""

    def __init__(self) -> None:
        """初始化 ConnectorRegistry。"""
        self._specs: dict[str, ConnectorSpec] = {}
        self._adapters: dict[str, Connector] = {}

    def register(self, spec: ConnectorSpec, adapter: Connector) -> ConnectorSpec:
        """注册连接器注册表。

        Args:
            spec: 资源规格定义。
            adapter: 适配器。

        Returns:
            连接器规格结果。

        Raises:
            ValueError: 输入值或业务状态不合法时抛出。
        """
        if adapter.name != spec.name:
            raise ValueError(
                f"Adapter name {adapter.name!r} does not match spec name {spec.name!r}"
            )
        self._specs[spec.connector_id] = spec
        self._adapters[spec.connector_id] = adapter
        return spec

    def get_spec(self, connector_id: str) -> ConnectorSpec | None:
        """获取规格。

        Args:
            connector_id: 连接器 ID。

        Returns:
            连接器规格无结果。
        """
        return self._specs.get(connector_id)

    def list_specs(self, tenant_id: str | None = None) -> list[ConnectorSpec]:
        """查询规格。

        Args:
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            结果列表。
        """
        if tenant_id is None:
            return list(self._specs.values())
        return [s for s in self._specs.values() if s.tenant_id == tenant_id]

    def get_adapter(self, connector_id: str) -> Connector | None:
        """获取适配器。

        Args:
            connector_id: 连接器 ID。

        Returns:
            连接器无结果。
        """
        return self._adapters.get(connector_id)

    def set_adapter(self, connector_id: str, adapter: Connector) -> None:
        """设置适配器。

        Args:
            connector_id: 连接器 ID。
            adapter: 适配器。
        """
        self._adapters[connector_id] = adapter

    async def load_from_repository(
        self,
        repository: Any,
        adapter_factory: Callable[[ConnectorSpec], Connector] | None = None,
    ) -> int:
        """加载从仓储。

        Args:
            repository: 数据仓储实现。
            adapter_factory: 适配器工厂。

        Returns:
            整数结果。
        """
        loaded = 0
        for spec in await repository.list_specs():
            self._specs[spec.connector_id] = spec
            if adapter_factory is not None:
                self._adapters[spec.connector_id] = adapter_factory(spec)
            loaded += 1
        return loaded

    async def health(self, connector_id: str) -> ConnectorHealth | None:
        """检查连接器注册表健康状态。

        Args:
            connector_id: 连接器 ID。

        Returns:
            连接器健康无结果。
        """
        adapter = self._adapters.get(connector_id)
        if adapter is None:
            return None
        return await adapter.health()

    async def list_health(self, tenant_id: str | None = None) -> list[ConnectorHealth]:
        """查询健康。

        Args:
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            结果列表。
        """
        specs = self.list_specs(tenant_id)
        results: list[ConnectorHealth] = []
        for spec in specs:
            adapter = self._adapters.get(spec.connector_id)
            if adapter is None:
                results.append(
                    ConnectorHealth(
                        connector_id=spec.connector_id,
                        healthy=False,
                        detail="adapter not bound",
                    )
                )
                continue
            results.append(await adapter.health())
        return results

    async def invoke(
        self,
        connector_id: str,
        action: str,
        payload: dict,
        context: ConnectorContext,
    ) -> ConnectorInvocationResult:
        """调用连接器注册表。

        Args:
            connector_id: 连接器 ID。
            action: 待执行动作名称。
            payload: 事件、工作流或请求载荷。
            context: 执行上下文。

        Returns:
            连接器结果结果。
        """
        spec = self._specs.get(connector_id)
        if spec is None:
            return ConnectorInvocationResult(
                connector_id=connector_id,
                action=action,
                ok=False,
                error="connector not registered",
            )
        if not spec.enabled:
            return ConnectorInvocationResult(
                connector_id=connector_id,
                action=action,
                ok=False,
                error="connector disabled",
            )
        if spec.allowed_actions and action not in spec.allowed_actions:
            return ConnectorInvocationResult(
                connector_id=connector_id,
                action=action,
                ok=False,
                error=f"action not allowed: {action}",
            )
        if context.tenant_id != spec.tenant_id:
            return ConnectorInvocationResult(
                connector_id=connector_id,
                action=action,
                ok=False,
                error="tenant mismatch",
            )
        adapter = self._adapters.get(connector_id)
        if adapter is None:
            return ConnectorInvocationResult(
                connector_id=connector_id,
                action=action,
                ok=False,
                error="adapter not bound",
            )
        return await adapter.invoke(action, payload, context)

    async def compensate(
        self,
        connector_id: str,
        action: str,
        payload: dict,
        context: ConnectorContext,
    ) -> ConnectorInvocationResult:
        """补偿连接器注册表。

        Args:
            connector_id: 连接器 ID。
            action: 待执行动作名称。
            payload: 事件、工作流或请求载荷。
            context: 执行上下文。

        Returns:
            连接器结果结果。
        """

        spec = self._specs.get(connector_id)
        if spec is None:
            return ConnectorInvocationResult(
                connector_id=connector_id,
                action=action,
                ok=False,
                error="connector not registered",
            )
        if not spec.enabled:
            return ConnectorInvocationResult(
                connector_id=connector_id,
                action=action,
                ok=False,
                error="connector disabled",
            )
        if spec.allowed_actions and action not in spec.allowed_actions:
            return ConnectorInvocationResult(
                connector_id=connector_id,
                action=action,
                ok=False,
                error=f"action not allowed: {action}",
            )
        if context.tenant_id != spec.tenant_id:
            return ConnectorInvocationResult(
                connector_id=connector_id,
                action=action,
                ok=False,
                error="tenant mismatch",
            )
        adapter = self._adapters.get(connector_id)
        if adapter is None:
            return ConnectorInvocationResult(
                connector_id=connector_id,
                action=action,
                ok=False,
                error="adapter not bound",
            )
        return await adapter.compensate(action, payload, context)
