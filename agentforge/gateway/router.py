"""路由模块。"""

import asyncio
import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Optional

from agentforge.gateway.complexity import ComplexityEstimator, RuleBasedComplexityEstimator
from agentforge.gateway.model_registry import ModelProfile, ModelRegistry

logger = logging.getLogger(__name__)


__all__ = ["ModelProfile", "ModelRegistry", "ModelRouteDecision", "SmartRouter"]


@dataclass
class ModelRouteDecision:
    """模型路由决策相关组件。

    Attributes:
        selected_model: 选中模型。
        scores_per_model: 评分模型。
        reason: 变更原因。
        scores_detail: 评分详情。
        complexity: 本次路由使用的复杂度分数。
        complexity_source: 复杂度来源,调用方传入或估计器计算。
        complexity_confidence: 复杂度估计的置信度。
        complexity_features: 参与估计的特征。
    """

    selected_model: str
    scores_per_model: dict[str, float]
    reason: str
    scores_detail: dict[str, dict] = field(default_factory=dict)
    complexity: float = 0.0
    complexity_source: str = "caller"
    complexity_confidence: float = 1.0
    complexity_features: dict[str, float] = field(default_factory=dict)


class SmartRouter:
    """智能相关组件。"""

    WEIGHTS = {"capability": 0.5, "cost": 0.3, "latency": 0.2}

    # 成本统计。
    COST_AND_LATENCY_FLOOR = 3.0

    CAPABILITY_COMPLEXITY_AMPLIFICATION = 0.6

    COMPLEXITY_WEIGHT_SHIFT = 0.35

    def __init__(
        self,
        registry: Optional[ModelRegistry] = None,
        estimator: Optional[ComplexityEstimator] = None,
        outcome_sink: Optional[Callable[[dict], None]] = None,
    ) -> None:
        """初始化 SmartRouter。

        Args:
            registry: 注册表实例。
            estimator: 复杂度估计器;业务模块可注入自己的实现。
            outcome_sink: 路由结果落库/上报回调,用于后续按业务训练。
        """
        self._registry = registry or ModelRegistry()
        self._estimator: ComplexityEstimator = estimator or RuleBasedComplexityEstimator()
        self._outcome_sink = outcome_sink
        self._routing_records: deque[dict] = deque(maxlen=10000)
        self._failure_counts: dict[str, list[bool]] = {}
        self._lock = asyncio.Lock()

    async def route(
        self,
        task_type: str,
        complexity: Optional[float] = None,
        input_text: str = "",
    ) -> ModelRouteDecision:
        """选择并返回模型路由。

        Args:
            task_type: 任务类型。
            complexity: 复杂度。
            input_text: 输入文本。

        Returns:
            模型路由决策结果。
        """
        if complexity is None:
            estimate = self._estimator.estimate(input_text, task_type)
            complexity = estimate.score
            complexity_source = "estimator"
            complexity_confidence = estimate.confidence
            complexity_features = dict(estimate.features)
            logger.info(
                "complexity_estimated %s",
                {
                    "task_type": task_type,
                    "score": round(complexity, 4),
                    "confidence": round(complexity_confidence, 4),
                    "reason": estimate.reason,
                },
            )
        else:
            complexity_source = "caller"
            complexity_confidence = 1.0
            complexity_features = {}
        complexity = max(0.0, min(1.0, complexity))

        available = self._registry.get_available()
        if not available:
            # 降级处理。
            minimax = self._registry.get("MiniMax")
            if minimax:
                minimax.is_available = True
            available = [minimax] if minimax else []

        weights = self._effective_weights(complexity)

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

        selected = max(scores, key=scores.get)
        reason = (
            f"Highest weighted score ({scores[selected]:.2f}) for "
            f"task_type={task_type}, complexity={complexity:.2f}"
        )

        logger.info(
            "route_decision %s",
            {
                "task_type": task_type,
                "complexity": round(complexity, 4),
                "source": complexity_source,
                "selected_model": selected,
                "scores": {k: round(v, 2) for k, v in scores.items()},
                "features": complexity_features,
            },
        )
        return ModelRouteDecision(
            selected_model=selected,
            scores_per_model={k: round(v, 2) for k, v in scores.items()},
            reason=reason,
            scores_detail=details,
            complexity=complexity,
            complexity_source=complexity_source,
            complexity_confidence=complexity_confidence,
            complexity_features=complexity_features,
        )

    def _effective_weights(self, complexity: float) -> dict[str, float]:
        """计算有效权重。

        Args:
            complexity: 复杂度。

        Returns:
            结构化结果字典。
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
        """计算评分能力。

        Args:
            model: 模型标识或模型对象。
            task_type: 任务类型。
            complexity: 复杂度。

        Returns:
            数值结果。
        """
        base = model.capability_score

        task_bonuses = {
            "reasoning": {"Qwen3-Pro": 0.5, "DeepSeek-V3": 0.3},
            "code_gen": {"DeepSeek-V3": 0.5, "Qwen3-Pro": 0.3},
            "long_context": {"Kimi": 1.0},
            "creative": {"Qwen3-Pro": 0.3, "GLM-5": 0.2},
            "classification": {"MiniMax": 0.5},
        }
        bonus = task_bonuses.get(task_type, {}).get(model.name, 0.0)
        raw = base + bonus

        capability_norm = min(1.0, raw / 10.0)
        complexity_factor = (
            1.0 + complexity * self.CAPABILITY_COMPLEXITY_AMPLIFICATION * capability_norm
        )

        return raw * complexity_factor

    def _score_cost(self, model: ModelProfile, all_models: list[ModelProfile]) -> float:
        """计算评分成本。

        Args:
            model: 模型标识或模型对象。
            all_models: 全部。

        Returns:
            数值结果。
        """
        min_cost = min(m.cost_per_1k_tokens for m in all_models)
        max_cost = max(m.cost_per_1k_tokens for m in all_models)
        if max_cost == min_cost:
            return 5.0
        # 成本统计。
        normalized = 10.0 * (1.0 - (model.cost_per_1k_tokens - min_cost) / (max_cost - min_cost))
        return max(normalized, self.COST_AND_LATENCY_FLOOR)

    def _score_latency(self, model: ModelProfile, all_models: list[ModelProfile]) -> float:
        """计算评分延迟。

        Args:
            model: 模型标识或模型对象。
            all_models: 全部。

        Returns:
            数值结果。
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
        """处理汇总。

        Args:
            capability: 能力。
            cost: 成本。
            latency: 输入参数。
            weights: 权重。

        Returns:
            数值结果。
        """
        if weights is None:
            weights = self.WEIGHTS
        return (
            weights["capability"] * capability
            + weights["cost"] * cost
            + weights["latency"] * latency
        )

    async def record_result(self, model_name: str, success: bool) -> None:
        """记录结果。

        Args:
            model_name: 模型名称。
            success: 成功。
        """
        async with self._lock:
            if model_name not in self._failure_counts:
                self._failure_counts[model_name] = []
            self._failure_counts[model_name].append(success)
            # 获取结果。
            self._failure_counts[model_name] = self._failure_counts[model_name][-20:]

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

    def record_outcome(
        self,
        *,
        task_type: str,
        selected_model: str,
        success: bool,
        quality: Optional[float] = None,
        cost: Optional[float] = None,
        complexity: Optional[float] = None,
        features: Optional[dict[str, float]] = None,
    ) -> None:
        """记录路由结果,为后续按业务训练复杂度模型准备数据。

        Args:
            task_type: 任务类型。
            selected_model: 本次选中的模型。
            success: 本次调用是否成功。
            quality: 质量评分,可选。
            cost: 成本,可选。
            complexity: 本次使用的复杂度,可选。
            features: 本次使用的特征,可选。
        """
        record = {
            "task_type": task_type,
            "selected_model": selected_model,
            "success": success,
            "quality": quality,
            "cost": cost,
            "complexity": complexity,
            "features": dict(features or {}),
        }
        self._routing_records.append(record)
        if self._outcome_sink is not None:
            self._outcome_sink(record)

    def get_routing_records(self) -> list[dict]:
        """返回内存中的路由记录,用于导出或离线训练。

        Returns:
            路由记录列表。
        """
        return list(self._routing_records)

    async def get_fallback(self, failed_model: str) -> Optional[str]:
        """获取智能。

        Args:
            failed_model: 失败模型。

        Returns:
            处理结果对象。
        """
        available = self._registry.get_available()
        candidates = [m for m in available if m.name != failed_model]
        if not candidates:
            return None
        # 失败状态。
        fallback = max(candidates, key=lambda m: m.capability_score)
        return fallback.name

    def get_preset_response(self) -> dict:
        """获取响应。

        Returns:
            结构化结果字典。
        """
        return {
            "result": (
                "Service temporarily unavailable. All models are experiencing issues. "
                "Please retry in a few minutes."
            ),
            "degraded": True,
            "fallback": "preset",
        }
