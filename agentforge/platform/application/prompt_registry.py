from __future__ import annotations

from agentforge.platform.domain.quality import PromptStatus, PromptTemplate


class PromptRegistry:
    """Prompt 模板版本注册表。

    内存实现：支持按 (name, version) 精确解析、按 name 解析当前激活版本、
    版本回退（publish 新版本时旧版本自动 DEPRECATED，仍可按版本号检索）。
    不落库；如需持久化版本历史，可在其上扩展仓储（属后续增量）。
    """

    def __init__(self) -> None:
        self._templates: dict[tuple[str, str], PromptTemplate] = {}

    def register(self, template: PromptTemplate) -> PromptTemplate:
        key = (template.name, template.version)
        self._templates[key] = template
        return template

    def publish(self, name: str, version: str) -> PromptTemplate:
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
        try:
            return self.resolve(name, version)
        except ValueError:
            return None

    def render(self, name: str, version: str | None = None, **kwargs) -> str:
        template = self.resolve(name, version)
        return template.render(**kwargs)

    def list_(self, name: str | None = None) -> list[PromptTemplate]:
        templates = [t for (n, _), t in self._templates.items() if name is None or n == name]
        return sorted(templates, key=lambda t: (t.name, t.version))

    def _require(self, name: str, version: str) -> PromptTemplate:
        template = self._templates.get((name, version))
        if template is None:
            raise ValueError(f"Unknown prompt template {name}@{version}")
        return template
