"""跨业务共享的风险等级。"""

from __future__ import annotations

from enum import Enum


class RiskLevel(str, Enum):
    """通用风险等级，用于审批、审计、策略与质量门禁。"""

    READ_ONLY = "read_only"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
