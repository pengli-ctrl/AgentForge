"""AgentForge 模型网关层：model_registry。

本模块负责 model_registry 相关能力，是 模型网关层 的组成部分。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 涉及租户、任务、审计或成本的数据必须保持隔离和可追踪。
- 关键路径应保留日志、指标或链路追踪信息。
- 主要类：ModelProfile、ModelRegistry。
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class ModelProfile:
    """ModelProfile。

    ModelProfile 封装相关领域行为，保持职责单一并降低调用方复杂度。

    主要成员：
    - name: str。
    - capability_score: float。
    - cost_per_1k_tokens: float。
    - avg_latency_ms: float。
    - max_context_length: int。
    - is_available: bool。
    - description: str。
    - specializations: list[str]。

    设计约束：
    - 保持接口稳定，避免调用方依赖内部实现细节。
    - 涉及隔离、审批、审计、成本或失败恢复的逻辑必须显式处理。
    """

    name: str
    capability_score: float  # 说明：该步骤用于实现上述逻辑并保证行为稳定。
    cost_per_1k_tokens: float  # 说明：该步骤用于实现上述逻辑并保证行为稳定。
    avg_latency_ms: float  # 说明：该步骤用于实现上述逻辑并保证行为稳定。
    max_context_length: int = 32000  # 说明：该步骤用于实现上述逻辑并保证行为稳定。
    is_available: bool = True  # 说明：该步骤用于实现上述逻辑并保证行为稳定。
    description: str = ""
    specializations: list[str] = field(default_factory=list)


class ModelRegistry:
    """ModelRegistry。

    ModelRegistry 是核心运行时组件，负责状态管理、调度和跨模块协作。

    主要成员：
    - 方法 get()。
    - 方法 get_available()。
    - 方法 mark_unavailable()。
    - 方法 mark_available()。
    - 方法 register_model()。
    - 方法 unregister_model()。
    - 方法 list_models()。
    - 方法 get_all_profiles()。
    - 方法 get_by_specialization()。
    - 方法 get_cheapest()。
    - 方法 get_fastest()。
    - 方法 get_most_capable()。
    - 方法 status_summary()。

    设计约束：
    - 保持接口稳定，避免调用方依赖内部实现细节。
    - 涉及隔离、审批、审计、成本或失败恢复的逻辑必须显式处理。
    """

    def __init__(self):
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Returns:
            None，函数执行后的结果。
        """
        self._models: dict[str, ModelProfile] = {}
        self._lock = asyncio.Lock()
        # 执行中状态。
        # 说明：该步骤用于实现上述逻辑并保证行为稳定。
        # 说明：该步骤用于实现上述逻辑并保证行为稳定。
        self._pending_recovery: dict[str, asyncio.Task] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        """执行 _register_defaults 对应的逻辑，并返回处理结果。

        Returns:
            None，函数执行后的结果。
        """
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
                max_context_length=200000,  # 说明：该步骤用于实现上述逻辑并保证行为稳定。
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
        """执行 get 对应的核心操作，并保持调用契约稳定。

        Args:
            name: str，调用方传入的 name 参数。

        Returns:
            Optional[ModelProfile]，函数执行后的结果。
        """
        return self._models.get(name)

    def get_available(self) -> list[ModelProfile]:
        """读取并返回指定数据，并返回调用方需要的结果。

        Returns:
            list[ModelProfile]，函数执行后的结果。
        """
        return [m for m in self._models.values() if m.is_available]

    async def mark_unavailable(self, name: str, duration_seconds: float = 900) -> None:
        """执行 mark_unavailable 对应的逻辑，并返回处理结果。

        Args:
            name: str，调用方传入的 name 参数。
            duration_seconds: float，调用方传入的 duration_seconds 参数。

        Returns:
            None，函数执行后的结果。
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

            # 说明：该步骤用于实现上述逻辑并保证行为稳定。
            recovery = asyncio.create_task(self._recover_model_after(name, duration_seconds))
            self._pending_recovery[name] = recovery

    async def _recover_model_after(self, name: str, duration_seconds: float) -> None:
        """执行 _recover_model_after 对应的逻辑，并返回处理结果。

        Args:
            name: str，调用方传入的 name 参数。
            duration_seconds: float，调用方传入的 duration_seconds 参数。

        Returns:
            None，函数执行后的结果。
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
        """执行 mark_available 对应的逻辑，并返回处理结果。

        Args:
            name: str，调用方传入的 name 参数。

        Returns:
            None，函数执行后的结果。
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
        """执行 register_model 对应的逻辑，并返回处理结果。

        Args:
            profile: ModelProfile，调用方传入的 profile 参数。

        Returns:
            None，函数执行后的结果。
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
        """执行 unregister_model 对应的逻辑，并返回处理结果。

        Args:
            name: str，调用方传入的 name 参数。

        Returns:
            bool，函数执行后的结果。
        """
        async with self._lock:
            if name in self._models:
                del self._models[name]
                logger.info("Unregistered model: %s", name)
                return True
            return False

    def list_models(self) -> list[str]:
        """查询并返回列表结果，并返回调用方需要的结果。

        Returns:
            list[str]，函数执行后的结果。
        """
        return list(self._models.keys())

    def get_all_profiles(self) -> list[ModelProfile]:
        """读取并返回指定数据，并返回调用方需要的结果。

        Returns:
            list[ModelProfile]，函数执行后的结果。
        """
        return list(self._models.values())

    def get_by_specialization(self, task_type: str) -> list[ModelProfile]:
        """读取并返回指定数据，并返回调用方需要的结果。

        Args:
            task_type: str，调用方传入的 task_type 参数。

        Returns:
            list[ModelProfile]，函数执行后的结果。
        """
        return [
            m for m in self._models.values() if m.is_available and task_type in m.specializations
        ]

    def get_cheapest(self) -> Optional[ModelProfile]:
        """读取并返回指定数据，并返回调用方需要的结果。

        Returns:
            Optional[ModelProfile]，函数执行后的结果。
        """
        available = self.get_available()
        if not available:
            return None
        return min(available, key=lambda m: m.cost_per_1k_tokens)

    def get_fastest(self) -> Optional[ModelProfile]:
        """读取并返回指定数据，并返回调用方需要的结果。

        Returns:
            Optional[ModelProfile]，函数执行后的结果。
        """
        available = self.get_available()
        if not available:
            return None
        return min(available, key=lambda m: m.avg_latency_ms)

    def get_most_capable(self) -> Optional[ModelProfile]:
        """读取并返回指定数据，并返回调用方需要的结果。

        Returns:
            Optional[ModelProfile]，函数执行后的结果。
        """
        available = self.get_available()
        if not available:
            return None
        return max(available, key=lambda m: m.capability_score)

    def status_summary(self) -> dict[str, Any]:
        """执行 status_summary 对应的逻辑，并返回处理结果。

        Returns:
            dict[str, Any]，函数执行后的结果。
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
