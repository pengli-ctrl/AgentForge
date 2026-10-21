"""插件加载器模块。"""

from __future__ import annotations

from collections.abc import Sequence
from importlib.metadata import entry_points
from typing import Any, cast

from agentforge.platform.sdk.module import BusinessModule

MODULE_ENTRY_POINT_GROUP = "agentforge.modules"


class PluginLoadError(RuntimeError):
    """插件加载错误相关组件。"""


def load_module_plugins(group: str = MODULE_ENTRY_POINT_GROUP) -> list[BusinessModule]:
    """加载模块。

    Args:
        group: 输入参数。

    Returns:
        结果列表。

    Raises:
        PluginLoadError: 操作无法完成时抛出。
    """
    discovered = entry_points()
    selected = (
        discovered.select(group=group)
        if hasattr(discovered, "select")
        else cast(Any, discovered).get(group, ())
    )
    modules: list[BusinessModule] = []
    for entry_point in selected:
        try:
            loaded = entry_point.load()
            candidates = _materialize(loaded)
        except Exception as exc:  # noqa: BLE001 - preserve plugin name in startup error
            raise PluginLoadError(
                f"failed to load module plugin {entry_point.name!r}: {exc}"
            ) from exc
        modules.extend(candidates)
    return modules


def _materialize(loaded: Any) -> list[BusinessModule]:
    """实体化数据。

    Args:
        loaded: 输入参数。

    Returns:
        结果列表。

    Raises:
        PluginLoadError: 操作无法完成时抛出。
    """
    if isinstance(loaded, Sequence) and not isinstance(loaded, (str, bytes)):
        modules: list[BusinessModule] = []
        for item in loaded:
            modules.extend(_materialize(item))
        return modules
    candidate = loaded() if isinstance(loaded, type) or callable(loaded) else loaded
    if isinstance(candidate, Sequence) and not isinstance(candidate, (str, bytes)):
        return _materialize(candidate)
    if not isinstance(candidate, BusinessModule):
        raise PluginLoadError("entry point must provide BusinessModule or a zero-argument factory")
    return [candidate]


__all__ = ["MODULE_ENTRY_POINT_GROUP", "PluginLoadError", "load_module_plugins"]
