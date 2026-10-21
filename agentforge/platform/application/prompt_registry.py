"""提示词注册表模块。"""

from __future__ import annotations

from agentforge.platform.domain.quality import PromptStatus, PromptTemplate


class PromptRegistry:
    """提示词注册表。"""

    def __init__(self) -> None:
        """初始化 PromptRegistry。"""
        self._templates: dict[tuple[str, str], PromptTemplate] = {}

    def register(self, template: PromptTemplate) -> PromptTemplate:
        """注册提示词。

        Args:
            template: 模板。

        Returns:
            提示词模板结果。
        """
        key = (template.name, template.version)
        self._templates[key] = template
        return template

    def publish(self, name: str, version: str) -> PromptTemplate:
        """发布提示词。

        Args:
            name: 资源或对象名称。
            version: 资源版本号。

        Returns:
            提示词模板结果。
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
        """解析提示词。

        Args:
            name: 资源或对象名称。
            version: 资源版本号。

        Returns:
            提示词模板结果。

        Raises:
            ValueError: 输入值或业务状态不合法时抛出。
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
        """获取提示词。

        Args:
            name: 资源或对象名称。
            version: 资源版本号。

        Returns:
            提示词模板无结果。
        """
        try:
            return self.resolve(name, version)
        except ValueError:
            return None

    def render(self, name: str, version: str | None = None, **kwargs) -> str:
        """渲染提示词。

        Args:
            name: 资源或对象名称。
            version: 资源版本号。
            kwargs: 关键字参数。

        Returns:
            字符串结果。
        """
        template = self.resolve(name, version)
        return template.render(**kwargs)

    def list_(self, name: str | None = None) -> list[PromptTemplate]:
        """查询提示词。

        Args:
            name: 资源或对象名称。

        Returns:
            结果列表。
        """
        templates = [t for (n, _), t in self._templates.items() if name is None or n == name]
        return sorted(templates, key=lambda t: (t.name, t.version))

    def _require(self, name: str, version: str) -> PromptTemplate:
        """执行校验。

        Args:
            name: 资源或对象名称。
            version: 资源版本号。

        Returns:
            提示词模板结果。

        Raises:
            ValueError: 输入值或业务状态不合法时抛出。
        """
        template = self._templates.get((name, version))
        if template is None:
            raise ValueError(f"Unknown prompt template {name}@{version}")
        return template
