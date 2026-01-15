"""AgentForge 模型网关层：router。

本模块负责 router 相关能力，是 模型网关层 的组成部分。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 涉及租户、任务、审计或成本的数据必须保持隔离和可追踪。
- 关键路径应保留日志、指标或链路追踪信息。
- 主要类：ModelRouteDecision、SmartRouter。
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Optional

from agentforge.gateway.model_registry import ModelProfile, ModelRegistry

logger = logging.getLogger(__name__)

# 说明：该步骤用于实现上述逻辑并保证行为稳定。
# Agent 注册与查询。
__all__ = ["ModelProfile", "ModelRegistry", "ModelRouteDecision", "SmartRouter"]


@dataclass
class ModelRouteDecision:
    """ModelRouteDecision。

    ModelRouteDecision 封装相关领域行为，保持职责单一并降低调用方复杂度。

    主要成员：
    - selected_model: str。
    - scores_per_model: dict[str, float]。
    - reason: str。
    - scores_detail: dict[str, dict]。

    设计约束：
    - 保持接口稳定，避免调用方依赖内部实现细节。
    - 涉及隔离、审批、审计、成本或失败恢复的逻辑必须显式处理。
    """

    selected_model: str
    scores_per_model: dict[str, float]  # 说明：该步骤用于实现上述逻辑并保证行为稳定。
    reason: str
    scores_detail: dict[str, dict] = field(default_factory=dict)  # 成本统计。


class SmartRouter:
    """SmartRouter。

    SmartRouter 定义 HTTP 路由，负责参数校验、鉴权、服务调用和响应组织。

    主要成员：
    - WEIGHTS: {'capability': 0.5, 'cost': 0.3, 'latency': 0.2}。
    - COST_AND_LATENCY_FLOOR: 3.0。
    - CAPABILITY_COMPLEXITY_AMPLIFICATION: 0.6。
    - COMPLEXITY_WEIGHT_SHIFT: 0.35。
    - 方法 route()。
    - 方法 record_result()。
    - 方法 get_fallback()。
    - 方法 get_preset_response()。

    设计约束：
    - 保持接口稳定，避免调用方依赖内部实现细节。
    - 涉及隔离、审批、审计、成本或失败恢复的逻辑必须显式处理。
    """

    WEIGHTS = {"capability": 0.5, "cost": 0.3, "latency": 0.2}

    # 成本统计。
    # 说明：该步骤用于实现上述逻辑并保证行为稳定。
    # 说明：该步骤用于实现上述逻辑并保证行为稳定。
    COST_AND_LATENCY_FLOOR = 3.0

    # 说明：该步骤用于实现上述逻辑并保证行为稳定。
    # 说明：该步骤用于实现上述逻辑并保证行为稳定。
    # 说明：该步骤用于实现上述逻辑并保证行为稳定。
    CAPABILITY_COMPLEXITY_AMPLIFICATION = 0.6

    # 说明：该步骤用于实现上述逻辑并保证行为稳定。
    # 说明：该步骤用于实现上述逻辑并保证行为稳定。
    # 说明：该步骤用于实现上述逻辑并保证行为稳定。
    COMPLEXITY_WEIGHT_SHIFT = 0.35

    def __init__(self, registry: Optional[ModelRegistry] = None):
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Args:
            registry: Optional[ModelRegistry]，调用方传入的 registry 参数。

        Returns:
            None，函数执行后的结果。
        """
        self._registry = registry or ModelRegistry()
        # 说明：该步骤用于实现上述逻辑并保证行为稳定。
        self._failure_counts: dict[str, list[bool]] = (
            {}
        )  # 说明：该步骤用于实现上述逻辑并保证行为稳定。
        self._lock = asyncio.Lock()

    async def route(
        self,
        task_type: str,
        complexity: float,
        input_text: str,
    ) -> ModelRouteDecision:
        """执行 route 对应的逻辑，并返回处理结果。

        Args:
            task_type: str，调用方传入的 task_type 参数。
            complexity: float，调用方传入的 complexity 参数。
            input_text: str，调用方传入的 input_text 参数。

        Returns:
            ModelRouteDecision，函数执行后的结果。
        """
        available = self._registry.get_available()
        if not available:
            # 降级处理。
            minimax = self._registry.get("MiniMax")
            if minimax:
                minimax.is_available = True  # 说明：该步骤用于实现上述逻辑并保证行为稳定。
            available = [minimax] if minimax else []

        weights = self._effective_weights(complexity)

        # 说明：该步骤用于实现上述逻辑并保证行为稳定。
        scores = {}
        details = {}

        for model in available:
            cap_score = self._score_capability(model, task_type, complexity)
            cost_score = self._score_cost(model, available)
            latency_score = self._score_latency(model, available)

            weighted = self._weighted_sum(cap_score, cost_score, latency_score, weights)
            scores[model.name] = weighted
            details[model.name] = {
                "capability": round(cap_score, 2),
                "cost": round(cost_score, 2),
                "latency": round(latency_score, 2),
            }

        # 说明：该步骤用于实现上述逻辑并保证行为稳定。
        selected = max(scores, key=scores.get)
        reason = (
            f"Highest weighted score ({scores[selected]:.2f}) for "
            f"task_type={task_type}, complexity={complexity:.2f}"
        )

        return ModelRouteDecision(
            selected_model=selected,
            scores_per_model={k: round(v, 2) for k, v in scores.items()},
            reason=reason,
            scores_detail=details,
        )

    def _effective_weights(self, complexity: float) -> dict[str, float]:
        """执行 _effective_weights 对应的逻辑，并返回处理结果。

        Args:
            complexity: float，调用方传入的 complexity 参数。

        Returns:
            dict[str, float]，函数执行后的结果。
        """
        cap_weight = self.WEIGHTS["capability"] + complexity * self.COMPLEXITY_WEIGHT_SHIFT
        cap_weight = max(0.0, min(1.0, cap_weight))
        remaining = 1.0 - cap_weight
        cost_lat_sum = self.WEIGHTS["cost"] + self.WEIGHTS["latency"]
        cost_weight = remaining * (self.WEIGHTS["cost"] / cost_lat_sum)
        latency_weight = remaining - cost_weight
        return {
            "capability": cap_weight,
            "cost": cost_weight,
            "latency": latency_weight,
        }

    def _score_capability(self, model: ModelProfile, task_type: str, complexity: float) -> float:
        """执行 _score_capability 对应的逻辑，并返回处理结果。

        Args:
            model: ModelProfile，调用方传入的 model 参数。
            task_type: str，调用方传入的 task_type 参数。
            complexity: float，调用方传入的 complexity 参数。

        Returns:
            float，函数执行后的结果。
        """
        base = model.capability_score

        # 说明：该步骤用于实现上述逻辑并保证行为稳定。
        task_bonuses = {
            "reasoning": {"Qwen3-Pro": 0.5, "DeepSeek-V3": 0.3},
            "code_gen": {"DeepSeek-V3": 0.5, "Qwen3-Pro": 0.3},
            "long_context": {"Kimi": 1.0},  # 说明：该步骤用于实现上述逻辑并保证行为稳定。
            "creative": {"Qwen3-Pro": 0.3, "GLM-5": 0.2},
            "classification": {"MiniMax": 0.5},  # 说明：该步骤用于实现上述逻辑并保证行为稳定。
        }
        bonus = task_bonuses.get(task_type, {}).get(model.name, 0.0)
        raw = base + bonus

        # 说明：该步骤用于实现上述逻辑并保证行为稳定。
        capability_norm = min(1.0, raw / 10.0)
        complexity_factor = (
            1.0 + complexity * self.CAPABILITY_COMPLEXITY_AMPLIFICATION * capability_norm
        )

        return raw * complexity_factor

    def _score_cost(self, model: ModelProfile, all_models: list[ModelProfile]) -> float:
        """执行 _score_cost 对应的逻辑，并返回处理结果。

        Args:
            model: ModelProfile，调用方传入的 model 参数。
            all_models: list[ModelProfile]，调用方传入的 all_models 参数。

        Returns:
            float，函数执行后的结果。
        """
        min_cost = min(m.cost_per_1k_tokens for m in all_models)
        max_cost = max(m.cost_per_1k_tokens for m in all_models)
        if max_cost == min_cost:
            return 5.0  # 成本统计。
        # 成本统计。
        normalized = 10.0 * (1.0 - (model.cost_per_1k_tokens - min_cost) / (max_cost - min_cost))
        return max(normalized, self.COST_AND_LATENCY_FLOOR)

    def _score_latency(self, model: ModelProfile, all_models: list[ModelProfile]) -> float:
        """执行 _score_latency 对应的逻辑，并返回处理结果。

        Args:
            model: ModelProfile，调用方传入的 model 参数。
            all_models: list[ModelProfile]，调用方传入的 all_models 参数。

        Returns:
            float，函数执行后的结果。
        """
        min_lat = min(m.avg_latency_ms for m in all_models)
        max_lat = max(m.avg_latency_ms for m in all_models)
        if max_lat == min_lat:
            return 5.0
        # 成本统计。
        normalized = 10.0 * (1.0 - (model.avg_latency_ms - min_lat) / (max_lat - min_lat))
        return max(normalized, self.COST_AND_LATENCY_FLOOR)

    def _weighted_sum(
        self,
        capability: float,
        cost: float,
        latency: float,
        weights: Optional[dict[str, float]] = None,
    ) -> float:
        """执行 _weighted_sum 对应的逻辑，并返回处理结果。

        Args:
            capability: float，调用方传入的 capability 参数。
            cost: float，调用方传入的 cost 参数。
            latency: float，调用方传入的 latency 参数。
            weights: Optional[dict[str, float]]，调用方传入的 weights 参数。

        Returns:
            float，函数执行后的结果。
        """
        if weights is None:
            weights = self.WEIGHTS
        return (
            weights["capability"] * capability
            + weights["cost"] * cost
            + weights["latency"] * latency
        )

    # 说明：该步骤用于实现上述逻辑并保证行为稳定。

    async def record_result(self, model_name: str, success: bool) -> None:
        """记录事件或指标，并返回调用方需要的结果。

        Args:
            model_name: str，调用方传入的 model_name 参数。
            success: bool，调用方传入的 success 参数。

        Returns:
            None，函数执行后的结果。
        """
        async with self._lock:
            if model_name not in self._failure_counts:
                self._failure_counts[model_name] = []
            self._failure_counts[model_name].append(success)
            # 获取结果。
            self._failure_counts[model_name] = self._failure_counts[model_name][-20:]

            # 说明：该步骤用于实现上述逻辑并保证行为稳定。
            recent = self._failure_counts[model_name][-10:]
            if len(recent) >= 10:
                failure_rate = sum(1 for s in recent if not s) / len(recent)
                if failure_rate > 0.5:
                    logger.warning(
                        "Circuit breaker triggered for %s: %.0f%% failure rate over last 10 calls",
                        model_name,
                        failure_rate * 100,
                    )
                    await self._registry.mark_unavailable(model_name, duration_seconds=900)

    # 降级处理。

    async def get_fallback(self, failed_model: str) -> Optional[str]:
        """读取并返回指定数据，并返回调用方需要的结果。

        Args:
            failed_model: str，调用方传入的 failed_model 参数。

        Returns:
            Optional[str]，函数执行后的结果。
        """
        available = self._registry.get_available()
        candidates = [m for m in available if m.name != failed_model]
        if not candidates:
            return None  # 失败状态。
        # 失败状态。
        fallback = max(candidates, key=lambda m: m.capability_score)
        return fallback.name

    def get_preset_response(self) -> dict:
        """读取并返回指定数据，并返回调用方需要的结果。

        Returns:
            dict，函数执行后的结果。
        """
        return {
            "result": (
                "Service temporarily unavailable. All models are experiencing issues. "
                "Please retry in a few minutes."
            ),
            "degraded": True,
            "fallback": "preset",
        }
