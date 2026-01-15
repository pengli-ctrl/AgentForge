"""AgentForge 平台应用服务层：connector_registry。

本模块封装 connector_registry 对应外部系统或基础设施协议，提供稳定、可替换的适配接口。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：Connector、ConnectorRegistry。
"""

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
    """Connector。

    Connector 封装外部系统或基础设施协议，向上提供稳定、可测试的接口。

    主要成员：
    - name: str。
    - version: str。
    - risk_level: str。
    - 方法 health()。
    - 方法 invoke()。
    - 方法 compensate()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    name: str
    version: str = "1.0"
    risk_level: str = "low"

    @abstractmethod
    async def health(self) -> ConnectorHealth:
        """执行 health 对应的逻辑，并返回处理结果。

        Returns:
            ConnectorHealth，函数执行后的结果。

        Raises:
            NotImplementedError: 当输入、状态或外部依赖不满足要求时抛出。
        """
        raise NotImplementedError

    @abstractmethod
    async def invoke(
        self,
        action: str,
        payload: dict,
        context: ConnectorContext,
    ) -> ConnectorInvocationResult:
        """执行 invoke 对应的逻辑，并返回处理结果。

        Args:
            action: str，调用方传入的 action 参数。
            payload: dict，调用方传入的 payload 参数。
            context: ConnectorContext，调用方传入的 context 参数。

        Returns:
            ConnectorInvocationResult，函数执行后的结果。

        Raises:
            NotImplementedError: 当输入、状态或外部依赖不满足要求时抛出。
        """
        raise NotImplementedError

    @abstractmethod
    async def compensate(
        self,
        action: str,
        payload: dict,
        context: ConnectorContext,
    ) -> ConnectorInvocationResult:
        """执行 compensate 对应的逻辑，并返回处理结果。

        Args:
            action: str，调用方传入的 action 参数。
            payload: dict，调用方传入的 payload 参数。
            context: ConnectorContext，调用方传入的 context 参数。

        Returns:
            ConnectorInvocationResult，函数执行后的结果。

        Raises:
            NotImplementedError: 当输入、状态或外部依赖不满足要求时抛出。
        """
        raise NotImplementedError


class ConnectorRegistry:
    """ConnectorRegistry。

    ConnectorRegistry 封装相关领域行为，保持职责单一并降低调用方复杂度。

    主要成员：
    - 方法 register()。
    - 方法 get_spec()。
    - 方法 list_specs()。
    - 方法 get_adapter()。
    - 方法 set_adapter()。
    - 方法 load_from_repository()。
    - 方法 health()。
    - 方法 list_health()。
    - 方法 invoke()。

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
        self._adapters: dict[str, Connector] = {}

    def register(self, spec: ConnectorSpec, adapter: Connector) -> ConnectorSpec:
        """执行 register 对应的逻辑，并返回处理结果。

        Args:
            spec: ConnectorSpec，调用方传入的 spec 参数。
            adapter: Connector，调用方传入的 adapter 参数。

        Returns:
            ConnectorSpec，函数执行后的结果。

        Raises:
            ValueError: 当输入、状态或外部依赖不满足要求时抛出。
        """
        if adapter.name != spec.name:
            raise ValueError(
                f"Adapter name {adapter.name!r} does not match spec name {spec.name!r}"
            )
        self._specs[spec.connector_id] = spec
        self._adapters[spec.connector_id] = adapter
        return spec

    def get_spec(self, connector_id: str) -> ConnectorSpec | None:
        """读取并返回指定数据，并返回调用方需要的结果。

        Args:
            connector_id: str，调用方传入的 connector_id 参数。

        Returns:
            ConnectorSpec | None，函数执行后的结果。
        """
        return self._specs.get(connector_id)

    def list_specs(self, tenant_id: str | None = None) -> list[ConnectorSpec]:
        """查询并返回列表结果，并返回调用方需要的结果。

        Args:
            tenant_id: str | None，调用方传入的 tenant_id 参数。

        Returns:
            list[ConnectorSpec]，函数执行后的结果。
        """
        if tenant_id is None:
            return list(self._specs.values())
        return [s for s in self._specs.values() if s.tenant_id == tenant_id]

    def get_adapter(self, connector_id: str) -> Connector | None:
        """读取并返回指定数据，并返回调用方需要的结果。

        Args:
            connector_id: str，调用方传入的 connector_id 参数。

        Returns:
            Connector | None，函数执行后的结果。
        """
        return self._adapters.get(connector_id)

    def set_adapter(self, connector_id: str, adapter: Connector) -> None:
        """执行 set_adapter 对应的逻辑，并返回处理结果。

        Args:
            connector_id: str，调用方传入的 connector_id 参数。
            adapter: Connector，调用方传入的 adapter 参数。

        Returns:
            None，函数执行后的结果。
        """
        self._adapters[connector_id] = adapter

    async def load_from_repository(
        self,
        repository: Any,
        adapter_factory: Callable[[ConnectorSpec], Connector] | None = None,
    ) -> int:
        """加载配置或资源，并返回调用方需要的结果。

        Args:
            repository: Any，调用方传入的 repository 参数。
            adapter_factory: Callable[[ConnectorSpec], Connector] | None，调用方传入的 adapter_factory 参数。

        Returns:
            int，函数执行后的结果。
        """
        loaded = 0
        for spec in await repository.list_specs():
            self._specs[spec.connector_id] = spec
            if adapter_factory is not None:
                self._adapters[spec.connector_id] = adapter_factory(spec)
            loaded += 1
        return loaded

    async def health(self, connector_id: str) -> ConnectorHealth | None:
        """执行 health 对应的逻辑，并返回处理结果。

        Args:
            connector_id: str，调用方传入的 connector_id 参数。

        Returns:
            ConnectorHealth | None，函数执行后的结果。
        """
        adapter = self._adapters.get(connector_id)
        if adapter is None:
            return None
        return await adapter.health()

    async def list_health(self, tenant_id: str | None = None) -> list[ConnectorHealth]:
        """查询并返回列表结果，并返回调用方需要的结果。

        Args:
            tenant_id: str | None，调用方传入的 tenant_id 参数。

        Returns:
            list[ConnectorHealth]，函数执行后的结果。
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
        """执行 invoke 对应的逻辑，并返回处理结果。

        Args:
            connector_id: str，调用方传入的 connector_id 参数。
            action: str，调用方传入的 action 参数。
            payload: dict，调用方传入的 payload 参数。
            context: ConnectorContext，调用方传入的 context 参数。

        Returns:
            ConnectorInvocationResult，函数执行后的结果。
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
