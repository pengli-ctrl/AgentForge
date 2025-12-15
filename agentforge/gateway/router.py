"""
5-model intelligent router — gateway layer core component.

Routes requests to the optimal model based on a 3-dimensional scoring matrix:
    Capability (weight 0.5): Model quality/accuracy for this task type
    Cost       (weight 0.3): Cost per 1K tokens (lower = better)
    Latency    (weight 0.2): Average response time in ms (lower = better)

Registered models:
    Qwen3-Pro:  capability=9.0, cost=$0.020/1K, latency=3000ms — premium quality
    GLM-5:      capability=8.0, cost=$0.015/1K, latency=2500ms — balanced
    Kimi:       capability=7.5, cost=$0.012/1K, latency=2000ms, max_context=200K
    MiniMax:    capability=5.0, cost=$0.002/1K, latency=800ms  — fast/cheap fallback
    DeepSeek-V3: capability=8.5, cost=$0.008/1K, latency=2000ms — best value

Degradation chain (on timeout/failure):
    Primary model → secondary → MiniMax (lightest) → preset response

Circuit breaker:
    If a model has >50% failure rate over last 10 consecutive calls,
    circuit opens for 15 minutes (skip model entirely).
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Optional

from agentforge.gateway.model_registry import ModelProfile, ModelRegistry

logger = logging.getLogger(__name__)

# Re-export for backward compatibility
# Other modules can still do: from agentforge.gateway.router import ModelProfile, ModelRegistry
__all__ = ["ModelProfile", "ModelRegistry", "ModelRouteDecision", "SmartRouter"]


@dataclass
class ModelRouteDecision:
    """
    Result of a model routing decision.

    Named ModelRouteDecision (not RouteDecision) to avoid naming conflict
    with workflow/llm_router.py's RouteDecision, which handles YAML workflow
    routing (a different concern from model selection).
    """

    selected_model: str
    scores_per_model: dict[str, float]  # model_name → weighted_score
    reason: str
    scores_detail: dict[str, dict] = field(
        default_factory=dict
    )  # model → {capability, cost, latency}


class SmartRouter:
    """
    3-dimensional scoring router with fallback chain and circuit breaker.

    Scoring algorithm:
        1. Capability is computed from the model's baseline plus a task-specific
           bonus, then amplified by a *capability-proportional* complexity factor
           (only genuinely capable models are further rewarded as tasks get
           harder). This prevents cheap low-capability models (e.g. MiniMax)
           from being swept up by a uniform complexity scaling.
        2. Cost and latency are inverted min-max normalized against the pool,
           but with a lower-bound floor so the most expensive / slowest model is
           never pinned to 0 — previously the relative normalization made the
           premium Qwen3-Pro score 0 on both dimensions and permanently lose to
           the budget model.
        3. Complexity shifts the weighting: at complexity=0 the base weights
           (0.5/0.3/0.2, matching README) keep simple tasks on the cheap/fast
           model (MiniMax); as complexity rises the capability weight grows so
           high-capability models (Qwen3-Pro) win hard tasks.
        4. Select the model with the highest weighted score.

    Why these weights?
        Capability (0.5) is most important — a wrong answer is worse than a slow one.
        Cost (0.3) matters for sustainability but shouldn't override quality.
        Latency (0.2) matters for UX but users tolerate 2–3s delays.
        For complex tasks capability is even more important, so the capability
        weight is raised by ComplexityWeightShift (up to +0.35 at complexity=1).

    Fallback chain on failure:
        Primary → Secondary (most capable available) → MiniMax (always fastest) → preset
    """

    WEIGHTS = {"capability": 0.5, "cost": 0.3, "latency": 0.2}

    # Lower-bound protection for cost/latency scores. Min-max normalization is
    # relative to the pool, so the most expensive/slowest model would otherwise
    # always score 0 and never be selected, no matter how capable it is.
    COST_AND_LATENCY_FLOOR = 3.0

    # How strongly (fraction of the 0..1 capability scale) complex tasks amplify a
    # model's capability. Proportional to the model's own capability so that only
    # genuinely capable models benefit — budget models are not swept up.
    CAPABILITY_COMPLEXITY_AMPLIFICATION = 0.6

    # Extra capability weight shifted in as complexity 0.0 → 1.0. Base weight is
    # WEIGHTS["capability"] (0.5); at max complexity it becomes 0.5 + 0.35 = 0.85,
    # making capability decisively dominant for hard tasks.
    COMPLEXITY_WEIGHT_SHIFT = 0.35

    def __init__(self, registry: Optional[ModelRegistry] = None):
        self._registry = registry or ModelRegistry()
        # Failure tracking per model for circuit breaker
        self._failure_counts: dict[str, list[bool]] = {}  # model → [success/failure booleans]
        self._lock = asyncio.Lock()

    async def route(
        self,
        task_type: str,
        complexity: float,
        input_text: str,
    ) -> ModelRouteDecision:
        """
        Route a request to the optimal model.

        Args:
            task_type: Category of task (e.g., "reasoning", "summarization",
                       "code_gen", "creative", "classification").
            complexity: Estimated complexity 0.0–1.0 (affects capability weight).
            input_text: The actual input (used for context length checking).

        Returns:
            RouteDecision with selected model and scoring details.
        """
        available = self._registry.get_available()
        if not available:
            # All models circuit-broken — emergency fallback to MiniMax
            minimax = self._registry.get("MiniMax")
            if minimax:
                minimax.is_available = True  # Force-restore
            available = [minimax] if minimax else []

        weights = self._effective_weights(complexity)

        # Compute scores for each available model
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

        # Select highest-scoring model
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
        """Compute dimension weights for the given complexity.

        At complexity=0 this returns the README base weights (0.5/0.3/0.2).
        As complexity rises, capability weight grows toward the base + shift,
        and cost/latency keep their relative proportion in the remainder. This is
        how complex tasks favor high-capability models without ever dropping the
        cost/latency dimensions entirely.
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
        """
        Capability score (0–10). Adjusted by task type and complexity.

        Task-specific bonuses:
        - Kimi gets a boost for long-context tasks (200K context window)
        - Qwen3-Pro gets a boost for reasoning tasks (highest baseline)
        - DeepSeek-V3 gets a boost for code generation tasks

        Complexity amplification is *capability-proportional*: the factor scales
        with the model's own capability so only high-capability models are
        rewarded on hard tasks. A cheap, low-capability fallback (MiniMax) is
        intentionally left unamplified, giving the premium capability models real
        room to win as complexity increases.
        """
        base = model.capability_score

        # Task-specific adjustments
        task_bonuses = {
            "reasoning": {"Qwen3-Pro": 0.5, "DeepSeek-V3": 0.3},
            "code_gen": {"DeepSeek-V3": 0.5, "Qwen3-Pro": 0.3},
            "long_context": {"Kimi": 1.0},  # 200K context is unique advantage
            "creative": {"Qwen3-Pro": 0.3, "GLM-5": 0.2},
            "classification": {"MiniMax": 0.5},  # Cheap model sufficient
        }
        bonus = task_bonuses.get(task_type, {}).get(model.name, 0.0)
        raw = base + bonus

        # Capability-proportional complexity amplification.
        capability_norm = min(1.0, raw / 10.0)
        complexity_factor = (
            1.0 + complexity * self.CAPABILITY_COMPLEXITY_AMPLIFICATION * capability_norm
        )

        return raw * complexity_factor

    def _score_cost(self, model: ModelProfile, all_models: list[ModelProfile]) -> float:
        """
        Cost score (0–10). Inverted: lower cost → higher score.
        Normalized relative to the most expensive model in the pool, with a
        lower-bound floor so the most expensive model is never scored 0.
        """
        min_cost = min(m.cost_per_1k_tokens for m in all_models)
        max_cost = max(m.cost_per_1k_tokens for m in all_models)
        if max_cost == min_cost:
            return 5.0  # All same cost
        # Invert: cheapest gets 10, most expensive gets COST_AND_LATENCY_FLOOR
        normalized = 10.0 * (1.0 - (model.cost_per_1k_tokens - min_cost) / (max_cost - min_cost))
        return max(normalized, self.COST_AND_LATENCY_FLOOR)

    def _score_latency(self, model: ModelProfile, all_models: list[ModelProfile]) -> float:
        """
        Latency score (0–10). Inverted: lower latency → higher score.
        Normalized relative to the slowest model in the pool, with a lower-bound
        floor so the slowest model is never scored 0.
        """
        min_lat = min(m.avg_latency_ms for m in all_models)
        max_lat = max(m.avg_latency_ms for m in all_models)
        if max_lat == min_lat:
            return 5.0
        # Invert: fastest gets 10, slowest gets COST_AND_LATENCY_FLOOR
        normalized = 10.0 * (1.0 - (model.avg_latency_ms - min_lat) / (max_lat - min_lat))
        return max(normalized, self.COST_AND_LATENCY_FLOOR)

    def _weighted_sum(
        self,
        capability: float,
        cost: float,
        latency: float,
        weights: Optional[dict[str, float]] = None,
    ) -> float:
        """Compute weighted score from three dimensions.

        If no weights are supplied the README base weights (0.5/0.3/0.2) are used;
        otherwise the caller-provided weights (already adjusted for complexity)
        drive the combination.
        """
        if weights is None:
            weights = self.WEIGHTS
        return (
            weights["capability"] * capability
            + weights["cost"] * cost
            + weights["latency"] * latency
        )

    # ── Failure tracking & circuit breaker ──────────────────────────────

    async def record_result(self, model_name: str, success: bool) -> None:
        """
        Record a model call result for circuit breaker tracking.

        If last 10 calls have >50% failure rate → circuit opens for 15min.
        """
        async with self._lock:
            if model_name not in self._failure_counts:
                self._failure_counts[model_name] = []
            self._failure_counts[model_name].append(success)
            # Keep only last 20 results
            self._failure_counts[model_name] = self._failure_counts[model_name][-20:]

            # Check circuit breaker: last 10 calls, >50% failure
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

    # ── Fallback chain ──────────────────────────────────────────────────

    async def get_fallback(self, failed_model: str) -> Optional[str]:
        """
        Get the next model in the fallback chain.

        The fallback chain is: next most capable → MiniMax (lightest) → None
        (preset response). We deliberately prefer capability over cost here: when
        the primary already failed, we want the best-quality backup, not the
        cheapest. Ordering by raw capability is stable and does not depend on task
        context, which this method does not receive.
        """
        available = self._registry.get_available()
        candidates = [m for m in available if m.name != failed_model]
        if not candidates:
            return None  # All models failed — use preset response
        # Return highest capability model as fallback (quality over cost when primary failed)
        fallback = max(candidates, key=lambda m: m.capability_score)
        return fallback.name

    def get_preset_response(self) -> dict:
        """Last-resort preset response when all models are unavailable."""
        return {
            "result": (
                "Service temporarily unavailable. All models are experiencing issues. "
                "Please retry in a few minutes."
            ),
            "degraded": True,
            "fallback": "preset",
        }
