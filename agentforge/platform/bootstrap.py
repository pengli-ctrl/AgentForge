from __future__ import annotations

from agentforge.platform.runtime import (
    ServiceContainer,
    build_memory_container,
    configure_container,
    get_container,
)


def build_default_container() -> ServiceContainer:
    return build_memory_container()


__all__ = [
    "ServiceContainer",
    "build_default_container",
    "build_memory_container",
    "configure_container",
    "get_container",
]
