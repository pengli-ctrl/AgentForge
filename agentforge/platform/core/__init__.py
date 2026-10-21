"""平台共享内核。

核心只依赖 SDK 中的协议，不依赖任何具体业务模块。
"""

from agentforge.platform.core.module_registry import (
    DEFAULT_CORE_CAPABILITIES,
    ModuleRegistrationError,
    ModuleRegistry,
    RegisteredModule,
)

__all__ = [
    "DEFAULT_CORE_CAPABILITIES",
    "ModuleRegistrationError",
    "ModuleRegistry",
    "RegisteredModule",
]
