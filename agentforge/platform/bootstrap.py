"""AgentForge 平台代码：bootstrap。

本模块负责 bootstrap 相关的平台能力，是 平台代码 的组成部分。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要函数：build_default_container。
"""

from __future__ import annotations

from agentforge.platform.runtime import (
    ServiceContainer,
    build_memory_container,
    configure_container,
    get_container,
)


def build_default_container() -> ServiceContainer:
    """构建目标对象，并返回调用方需要的结果。

    Returns:
        ServiceContainer，函数执行后的结果。
    """
    return build_memory_container()


__all__ = [
    "ServiceContainer",
    "build_default_container",
    "build_memory_container",
    "configure_container",
    "get_container",
]
