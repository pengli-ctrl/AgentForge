"""AgentForge 安全模块 — 四层容错防线的实现。

四类故障模式的容错设计：
- Trust Boundary：阻断 LLM 幻觉的跨 Agent 传播
- Conflict Arbiter：防止双 Agent 目标冲突导致的活跃锁
- AIMD Controller：全局协调重试行为，防止拥塞崩溃
- Pulse Shaper：平滑并发任务的统计同步脉冲
"""

from agentforge.safety.aimd_controller import AIMDRetryController
from agentforge.safety.conflict_arbiter import ConflictArbiter
from agentforge.safety.pulse_shaper import PulseShaper
from agentforge.safety.trust_boundary import FieldRef, TrustBoundary, ValidationResult

__all__ = [
    "TrustBoundary",
    "ValidationResult",
    "FieldRef",
    "ConflictArbiter",
    "AIMDRetryController",
    "PulseShaper",
]
