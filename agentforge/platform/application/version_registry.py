"""AgentForge 平台应用服务层：version_registry。

本模块负责 version_registry 相关的平台能力，是 平台应用服务层 的组成部分。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：ModelVersionRegistry。
"""

from __future__ import annotations

from agentforge.platform.domain.quality import ModelVersion, ModelVersionStatus


class ModelVersionRegistry:
    """ModelVersionRegistry。

    ModelVersionRegistry 封装相关领域行为，保持职责单一并降低调用方复杂度。

    主要成员：
    - 方法 register()。
    - 方法 resolve()。
    - 方法 get()。
    - 方法 retire()。
    - 方法 list_()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    def __init__(self) -> None:
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Returns:
            None，函数执行后的结果。
        """
        self._versions: dict[tuple[str, str], ModelVersion] = {}

    def register(self, version: ModelVersion) -> ModelVersion:
        """执行 register 对应的逻辑，并返回处理结果。

        Args:
            version: ModelVersion，调用方传入的 version 参数。

        Returns:
            ModelVersion，函数执行后的结果。
        """
        key = (version.name, version.version)
        self._versions[key] = version
        return version

    def resolve(self, name: str) -> ModelVersion:
        """执行 resolve 对应的逻辑，并返回处理结果。

        Args:
            name: str，调用方传入的 name 参数。

        Returns:
            ModelVersion，函数执行后的结果。

        Raises:
            ValueError: 当输入、状态或外部依赖不满足要求时抛出。
        """
        available = [
            v
            for (n, _), v in self._versions.items()
            if n == name and v.is_available and v.status == ModelVersionStatus.AVAILABLE
        ]
        if not available:
            raise ValueError(f"No available model version for name: {name}")
        # 能力分最高的版本视为"当前"，行为确定。
        return sorted(available, key=lambda v: v.capability_score)[-1]

    def get(self, name: str, version: str | None = None) -> ModelVersion | None:
        """执行 get 对应的核心操作，并保持调用契约稳定。

        Args:
            name: str，调用方传入的 name 参数。
            version: str | None，调用方传入的 version 参数。

        Returns:
            ModelVersion | None，函数执行后的结果。
        """
        if version is not None:
            try:
                return self._require(name, version)
            except ValueError:
                return None
        try:
            return self.resolve(name)
        except ValueError:
            return None

    def retire(self, name: str, version: str) -> ModelVersion:
        """执行 retire 对应的逻辑，并返回处理结果。

        Args:
            name: str，调用方传入的 name 参数。
            version: str，调用方传入的 version 参数。

        Returns:
            ModelVersion，函数执行后的结果。
        """
        model = self._require(name, version)
        model.status = ModelVersionStatus.RETIRED
        model.is_available = False
        return model

    def list_(self, name: str | None = None) -> list[ModelVersion]:
        """查询并返回列表结果，并返回调用方需要的结果。

        Args:
            name: str | None，调用方传入的 name 参数。

        Returns:
            list[ModelVersion]，函数执行后的结果。
        """
        versions = [v for (n, _), v in self._versions.items() if name is None or n == name]
        return sorted(versions, key=lambda v: (v.name, v.version))

    def _require(self, name: str, version: str) -> ModelVersion:
        """执行 _require 对应的逻辑，并返回处理结果。

        Args:
            name: str，调用方传入的 name 参数。
            version: str，调用方传入的 version 参数。

        Returns:
            ModelVersion，函数执行后的结果。

        Raises:
            ValueError: 当输入、状态或外部依赖不满足要求时抛出。
        """
        model = self._versions.get((name, version))
        if model is None:
            raise ValueError(f"Unknown model version {name}@{version}")
        return model
