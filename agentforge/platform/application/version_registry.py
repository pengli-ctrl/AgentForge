from __future__ import annotations

from agentforge.platform.domain.quality import ModelVersion, ModelVersionStatus


class ModelVersionRegistry:
    """模型版本注册表。

    内存实现：按 (name, version) 注册，可按名称解析当前可用版本、
    按任务类型筛选，并支持显式回退到旧版本（通过发布新的可用版本标记）。
    不落库；持久化版本历史属后续增量。
    """

    def __init__(self) -> None:
        self._versions: dict[tuple[str, str], ModelVersion] = {}

    def register(self, version: ModelVersion) -> ModelVersion:
        key = (version.name, version.version)
        self._versions[key] = version
        return version

    def resolve(self, name: str) -> ModelVersion:
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
        model = self._require(name, version)
        model.status = ModelVersionStatus.RETIRED
        model.is_available = False
        return model

    def list_(self, name: str | None = None) -> list[ModelVersion]:
        versions = [v for (n, _), v in self._versions.items() if name is None or n == name]
        return sorted(versions, key=lambda v: (v.name, v.version))

    def _require(self, name: str, version: str) -> ModelVersion:
        model = self._versions.get((name, version))
        if model is None:
            raise ValueError(f"Unknown model version {name}@{version}")
        return model
