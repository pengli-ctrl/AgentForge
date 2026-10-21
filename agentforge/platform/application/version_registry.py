"""版本注册表模块。"""

from __future__ import annotations

from agentforge.platform.domain.quality import ModelVersion, ModelVersionStatus


class ModelVersionRegistry:
    """模型版本注册表。"""

    def __init__(self) -> None:
        """初始化 ModelVersionRegistry。"""
        self._versions: dict[tuple[str, str], ModelVersion] = {}

    def register(self, version: ModelVersion) -> ModelVersion:
        """注册模型版本。

        Args:
            version: 资源版本号。

        Returns:
            模型版本结果。
        """
        key = (version.name, version.version)
        self._versions[key] = version
        return version

    def resolve(self, name: str) -> ModelVersion:
        """解析模型版本。

        Args:
            name: 资源或对象名称。

        Returns:
            模型版本结果。

        Raises:
            ValueError: 输入值或业务状态不合法时抛出。
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
        """读取模型版本。

        Args:
            name: 资源或对象名称。
            version: 资源版本号。

        Returns:
            模型版本无结果。
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
        """停用模型版本。

        Args:
            name: 资源或对象名称。
            version: 资源版本号。

        Returns:
            模型版本结果。
        """
        model = self._require(name, version)
        model.status = ModelVersionStatus.RETIRED
        model.is_available = False
        return model

    def list_(self, name: str | None = None) -> list[ModelVersion]:
        """查询模型版本。

        Args:
            name: 资源或对象名称。

        Returns:
            结果列表。
        """
        versions = [v for (n, _), v in self._versions.items() if name is None or n == name]
        return sorted(versions, key=lambda v: (v.name, v.version))

    def _require(self, name: str, version: str) -> ModelVersion:
        """执行校验。

        Args:
            name: 资源或对象名称。
            version: 资源版本号。

        Returns:
            模型版本结果。

        Raises:
            ValueError: 输入值或业务状态不合法时抛出。
        """
        model = self._versions.get((name, version))
        if model is None:
            raise ValueError(f"Unknown model version {name}@{version}")
        return model
