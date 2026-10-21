"""模型注册表模块。"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class ModelProfile:
    """模型配置相关组件。

    Attributes:
        name: 名称。
        capability_score: 能力评分。
        cost_per_1k_tokens: 成本。
        avg_latency_ms: 延迟毫秒。
        max_context_length: 最大上下文。
        is_available: 是否可用。
        description: 描述信息。
        specializations: 字段值。
    """

    name: str
    capability_score: float
    cost_per_1k_tokens: float
    avg_latency_ms: float
    max_context_length: int = 32000
    is_available: bool = True
    description: str = ""
    specializations: list[str] = field(default_factory=list)


class ModelRegistry:
    """模型注册表。"""

    def __init__(self):
        """初始化 ModelRegistry。"""
        self._models: dict[str, ModelProfile] = {}
        self._lock = asyncio.Lock()
        # 执行中状态。
        self._pending_recovery: dict[str, asyncio.Task] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        """注册默认项。"""
        defaults = [
            ModelProfile(
                name="Qwen3-Pro",
                capability_score=9.0,
                cost_per_1k_tokens=0.020,
                avg_latency_ms=3000,
                max_context_length=32000,
                description="Premium quality, best for complex reasoning and creative tasks",
                specializations=["reasoning", "creative", "code_gen"],
            ),
            ModelProfile(
                name="GLM-5",
                capability_score=8.0,
                cost_per_1k_tokens=0.015,
                avg_latency_ms=2500,
                max_context_length=32000,
                description="Balanced general-purpose model",
                specializations=["reasoning", "creative"],
            ),
            ModelProfile(
                name="Kimi",
                capability_score=7.5,
                cost_per_1k_tokens=0.012,
                avg_latency_ms=2000,
                max_context_length=200000,
                description="200K context window — best for long-document processing",
                specializations=["long_context", "summarization"],
            ),
            ModelProfile(
                name="MiniMax",
                capability_score=5.0,
                cost_per_1k_tokens=0.002,
                avg_latency_ms=800,
                max_context_length=16000,
                description="Fast and cheap — ideal for simple tasks and fallback",
                specializations=["classification", "simple_extraction"],
            ),
            ModelProfile(
                name="DeepSeek-V3",
                capability_score=8.5,
                cost_per_1k_tokens=0.008,
                avg_latency_ms=2000,
                max_context_length=64000,
                description="Best price/performance ratio — excellent for code generation",
                specializations=["code_gen", "reasoning"],
            ),
        ]
        for model in defaults:
            self._models[model.name] = model

    def get(self, name: str) -> Optional[ModelProfile]:
        """读取模型。

        Args:
            name: 资源或对象名称。

        Returns:
            处理结果对象。
        """
        return self._models.get(name)

    def get_available(self) -> list[ModelProfile]:
        """读取可用。

        Returns:
            结果列表。
        """
        return [m for m in self._models.values() if m.is_available]

    async def mark_unavailable(self, name: str, duration_seconds: float = 900) -> None:
        """标记不可用。

        Args:
            name: 资源或对象名称。
            duration_seconds: 输入参数。
        """
        async with self._lock:
            model = self._models.get(name)
            if not model:
                return

            model.is_available = False
            logger.warning("Circuit breaker: %s unavailable for %.0fs", name, duration_seconds)

            # 取消任务。
            previous = self._pending_recovery.pop(name, None)
            if previous is not None and not previous.done():
                previous.cancel()

            recovery = asyncio.create_task(self._recover_model_after(name, duration_seconds))
            self._pending_recovery[name] = recovery

    async def _recover_model_after(self, name: str, duration_seconds: float) -> None:
        """处理模型之后。

        Args:
            name: 资源或对象名称。
            duration_seconds: 输入参数。
        """
        try:
            await asyncio.sleep(duration_seconds)
        except asyncio.CancelledError:
            return

        async with self._lock:
            current_task = asyncio.current_task()
            if self._pending_recovery.get(name) is not current_task:
                return
            model = self._models.get(name)
            if model is None:
                return
            model.is_available = True
            self._pending_recovery.pop(name, None)
            logger.info("Circuit breaker: %s recovered", name)

    async def mark_available(self, name: str) -> None:
        """标记可用。

        Args:
            name: 资源或对象名称。
        """
        async with self._lock:
            model = self._models.get(name)
            if model is None:
                return
            model.is_available = True
            pending = self._pending_recovery.pop(name, None)
            if pending is not None and not pending.done():
                pending.cancel()
            logger.info("Model %s marked available (cancelled pending recovery)", name)

    async def register_model(self, profile: ModelProfile) -> None:
        """注册模型。

        Args:
            profile: 配置。
        """
        async with self._lock:
            if profile.name in self._models:
                logger.warning("Model '%s' already registered, overwriting", profile.name)
            self._models[profile.name] = profile
            logger.info(
                "Registered model: %s (capability=%.1f, cost=%.4f/1K)",
                profile.name,
                profile.capability_score,
                profile.cost_per_1k_tokens,
            )

    async def unregister_model(self, name: str) -> bool:
        """注销模型。

        Args:
            name: 资源或对象名称。

        Returns:
            操作是否成功。
        """
        async with self._lock:
            if name in self._models:
                del self._models[name]
                logger.info("Unregistered model: %s", name)
                return True
            return False

    def list_models(self) -> list[str]:
        """查询数据模型。

        Returns:
            结果列表。
        """
        return list(self._models.keys())

    def get_all_profiles(self) -> list[ModelProfile]:
        """获取全部。

        Returns:
            结果列表。
        """
        return list(self._models.values())

    def get_by_specialization(self, task_type: str) -> list[ModelProfile]:
        """获取由。

        Args:
            task_type: 任务类型。

        Returns:
            结果列表。
        """
        return [
            m for m in self._models.values() if m.is_available and task_type in m.specializations
        ]

    def get_cheapest(self) -> Optional[ModelProfile]:
        """获取模型。

        Returns:
            处理结果对象。
        """
        available = self.get_available()
        if not available:
            return None
        return min(available, key=lambda m: m.cost_per_1k_tokens)

    def get_fastest(self) -> Optional[ModelProfile]:
        """获取模型。

        Returns:
            处理结果对象。
        """
        available = self.get_available()
        if not available:
            return None
        return min(available, key=lambda m: m.avg_latency_ms)

    def get_most_capable(self) -> Optional[ModelProfile]:
        """获取模型。

        Returns:
            处理结果对象。
        """
        available = self.get_available()
        if not available:
            return None
        return max(available, key=lambda m: m.capability_score)

    def status_summary(self) -> dict[str, Any]:
        """获取状态摘要。

        Returns:
            结构化结果字典。
        """
        total = len(self._models)
        available = len(self.get_available())
        return {
            "total_models": total,
            "available": available,
            "circuit_broken": total - available,
            "models": {
                name: {
                    "available": m.is_available,
                    "capability": m.capability_score,
                    "cost_per_1k": m.cost_per_1k_tokens,
                    "latency_ms": m.avg_latency_ms,
                }
                for name, m in self._models.items()
            },
        }
