"""AgentForge 平台应用服务层：prompt_registry。

本模块负责 prompt_registry 相关的平台能力，是 平台应用服务层 的组成部分。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：PromptRegistry。
"""

from __future__ import annotations

from agentforge.platform.domain.quality import PromptStatus, PromptTemplate


class PromptRegistry:
    """PromptRegistry。

    PromptRegistry 封装相关领域行为，保持职责单一并降低调用方复杂度。

    主要成员：
    - 方法 register()。
    - 方法 publish()。
    - 方法 resolve()。
    - 方法 get()。
    - 方法 render()。
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
        self._templates: dict[tuple[str, str], PromptTemplate] = {}

    def register(self, template: PromptTemplate) -> PromptTemplate:
        """执行 register 对应的逻辑，并返回处理结果。

        Args:
            template: PromptTemplate，调用方传入的 template 参数。

        Returns:
            PromptTemplate，函数执行后的结果。
        """
        key = (template.name, template.version)
        self._templates[key] = template
        return template

    def publish(self, name: str, version: str) -> PromptTemplate:
        """执行 publish 对应的核心操作，并保持调用契约稳定。

        Args:
            name: str，调用方传入的 name 参数。
            version: str，调用方传入的 version 参数。

        Returns:
            PromptTemplate，函数执行后的结果。
        """
        template = self._require(name, version)
        if template.status == PromptStatus.ACTIVE:
            return template
        # 同名的其它已激活版本降级为 DEPRECATED，保证同一时刻只有一个 ACTIVE。
        # 仍处于 DRAFT 的版本保持不变（尚未发布的草稿）。
        for (n, v), candidate in self._templates.items():
            if n == name and v != version and candidate.status == PromptStatus.ACTIVE:
                candidate.status = PromptStatus.DEPRECATED
        if template.status == PromptStatus.DRAFT:
            template.status = PromptStatus.ACTIVE
        return template

    def resolve(self, name: str, version: str | None = None) -> PromptTemplate:
        """执行 resolve 对应的逻辑，并返回处理结果。

        Args:
            name: str，调用方传入的 name 参数。
            version: str | None，调用方传入的 version 参数。

        Returns:
            PromptTemplate，函数执行后的结果。

        Raises:
            ValueError: 当输入、状态或外部依赖不满足要求时抛出。
        """
        if version is not None:
            return self._require(name, version)
        active = [
            t
            for (n, _), t in self._templates.items()
            if n == name and t.status == PromptStatus.ACTIVE
        ]
        if active:
            # 同一时刻仅一个 ACTIVE，取第一个即可。
            return sorted(active, key=lambda t: t.version)[-1]
        raise ValueError(f"No active prompt template for name: {name}")

    def get(self, name: str, version: str | None = None) -> PromptTemplate | None:
        """执行 get 对应的核心操作，并保持调用契约稳定。

        Args:
            name: str，调用方传入的 name 参数。
            version: str | None，调用方传入的 version 参数。

        Returns:
            PromptTemplate | None，函数执行后的结果。
        """
        try:
            return self.resolve(name, version)
        except ValueError:
            return None

    def render(self, name: str, version: str | None = None, **kwargs) -> str:
        """执行 render 对应的逻辑，并返回处理结果。

        Args:
            name: str，调用方传入的 name 参数。
            version: str | None，调用方传入的 version 参数。
            **kwargs: Any，调用方传入的 **kwargs 参数。

        Returns:
            str，函数执行后的结果。
        """
        template = self.resolve(name, version)
        return template.render(**kwargs)

    def list_(self, name: str | None = None) -> list[PromptTemplate]:
        """查询并返回列表结果，并返回调用方需要的结果。

        Args:
            name: str | None，调用方传入的 name 参数。

        Returns:
            list[PromptTemplate]，函数执行后的结果。
        """
        templates = [t for (n, _), t in self._templates.items() if name is None or n == name]
        return sorted(templates, key=lambda t: (t.name, t.version))

    def _require(self, name: str, version: str) -> PromptTemplate:
        """执行 _require 对应的逻辑，并返回处理结果。

        Args:
            name: str，调用方传入的 name 参数。
            version: str，调用方传入的 version 参数。

        Returns:
            PromptTemplate，函数执行后的结果。

        Raises:
            ValueError: 当输入、状态或外部依赖不满足要求时抛出。
        """
        template = self._templates.get((name, version))
        if template is None:
            raise ValueError(f"Unknown prompt template {name}@{version}")
        return template
