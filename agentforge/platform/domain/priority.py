"""跨业务共享的优先级等级。"""

from __future__ import annotations

from enum import Enum


class PriorityLevel(str, Enum):
    """通用优先级，业务模块可映射到自己的语义。"""

    P0 = "p0"
    P1 = "p1"
    P2 = "p2"
    P3 = "p3"
